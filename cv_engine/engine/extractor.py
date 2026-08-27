import os
import sys
import json
import math
import cv2
import numpy as np
import supervision as sv
from ultralytics import YOLO

# Add the parent and base repo directories to Python path for seamless importing
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "football_analysis_base"))

from cv_engine.engine.classifier import TeamClassifier
from cv_engine.engine.device import resolve_device
from cv_engine.football_analysis_base.utils.bbox_utils import get_center_of_bbox, get_foot_position

class CameraTracker:
    def __init__(self):
        self.prev_gray = None
        self.prev_pts = None
        self.cumulative_dx = 0.0
        self.cumulative_dy = 0.0
        self.lk_params = dict(
            winSize=(15, 15),
            maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
        )
        self.feature_params = dict(
            maxCorners=100,
            qualityLevel=0.3,
            minDistance=3,
            blockSize=7
        )

    def update(self, frame):
        """
        Track frame-to-frame shift using sparse optical flow.
        Returns the cumulative shift (cumulative_dx, cumulative_dy).
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Track features outside the pitch (left/right margins) to avoid moving player noise
        mask = np.zeros_like(gray)
        mask[:, 0:int(w * 0.1)] = 1
        mask[:, int(w * 0.9):] = 1

        dx, dy = 0.0, 0.0

        if self.prev_gray is not None and self.prev_pts is not None and len(self.prev_pts) > 0:
            next_pts, status, _ = cv2.calcOpticalFlowPyrLK(
                self.prev_gray, gray, self.prev_pts, None, **self.lk_params
            )

            # Select successfully tracked points
            valid_prev = self.prev_pts[status == 1]
            valid_next = next_pts[status == 1]

            if len(valid_prev) >= 5:
                translations = valid_next - valid_prev
                dx = float(np.median(translations[:, 0]))
                dy = float(np.median(translations[:, 1]))

                # Check for camera cuts or abrupt changes
                if abs(dx) > 100 or abs(dy) > 100:
                    dx, dy = 0.0, 0.0
                else:
                    self.cumulative_dx += dx
                    self.cumulative_dy += dy

        # Re-detect features for the next frame
        self.prev_pts = cv2.goodFeaturesToTrack(gray, mask=mask, **self.feature_params)
        self.prev_gray = gray.copy()

        return self.cumulative_dx, self.cumulative_dy

class CoordinatesExtractor:
    def __init__(self, model_path="cv_engine/football_analysis_base/models/best.pt", warmup_frames=50):
        # Resolve model path relative to app root if needed
        if not os.path.exists(model_path):
            # Try loading relative to active directory
            alternative_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "football_analysis_base", "models", "best.pt")
            if os.path.exists(alternative_path):
                model_path = alternative_path

        self.device = resolve_device()
        self.model = YOLO(model_path)
        self.model.to(self.device)
        self.tracker = sv.ByteTrack()
        self.classifier = TeamClassifier(warmup_frames=warmup_frames)
        self.camera_tracker = CameraTracker()

        # Setup Default Homography.
        # These pixel vertices were digitised on ~1920x1080 broadcast footage. Any clip at a
        # different resolution must have them rescaled first, otherwise every projected point
        # collapses into a small sub-region of the pitch. See extract_coordinates().
        self.reference_size = (1920.0, 1080.0)
        self.pixel_vertices = np.array(
            [[110, 1035], [265, 275], [910, 260], [1614, 950]], dtype=np.float32
        )
        self.target_vertices = np.array(
            [[0, 68], [0, 0], [105, 0], [105, 68]], dtype=np.float32
        )
        self.default_H = cv2.getPerspectiveTransform(self.pixel_vertices, self.target_vertices)

        # Populated per-video by extract_coordinates()
        self.active_H = self.default_H
        self.video_fps = 25.0

    def homography_for_size(self, frame_w, frame_h):
        """
        Rescale the default pixel vertices from the reference resolution to the video's actual
        resolution and rebuild the homography. Returns default_H unchanged when the size matches
        or cannot be determined.
        """
        ref_w, ref_h = self.reference_size
        if not frame_w or not frame_h:
            return self.default_H
        if (float(frame_w), float(frame_h)) == (ref_w, ref_h):
            return self.default_H

        scale = np.array([frame_w / ref_w, frame_h / ref_h], dtype=np.float32)
        scaled_vertices = (self.pixel_vertices * scale).astype(np.float32)
        return cv2.getPerspectiveTransform(scaled_vertices, self.target_vertices)

    def project_point(self, H, x, y):
        """
        Map a single pixel point (x, y) to top-down pitch coordinates using homography matrix H.
        Clips the resulting coordinate to the pitch boundaries [0-105] and [0-68].
        """
        pt = np.array([x, y, 1.0], dtype=np.float32)
        projected = H @ pt
        if projected[2] != 0:
            projected /= projected[2]

        x_pitch = max(0.0, min(105.0, float(projected[0])))
        y_pitch = max(0.0, min(68.0, float(projected[1])))
        return x_pitch, y_pitch

    def extract_coordinates(self, video_path, calibration_config=None):
        """
        Generator yielding coordinate batches (up to 500 coordinates per batch).
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found at: {video_path}")

        # Load configuration
        H = None
        gk_overrides = {}
        if calibration_config:
            if "homography_matrix" in calibration_config:
                # An explicitly calibrated matrix always wins - it was measured against this
                # footage, so rescaling it would corrupt it.
                H = np.array(calibration_config["homography_matrix"], dtype=np.float32)
            if "gk_overrides" in calibration_config:
                # Convert string keys to int player IDs
                gk_overrides = {int(k): v for k, v in calibration_config["gk_overrides"].items()}

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError(f"Failed to open video file: {video_path}")

        frame_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        frame_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

        if H is None:
            H = self.homography_for_size(frame_w, frame_h)
        self.active_H = H

        # Frame rate drives every speed threshold downstream (sprint, shot, possession timeout).
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps and fps > 0 and not math.isnan(fps):
            self.video_fps = float(fps)
        else:
            self.video_fps = 25.0

        # A short clip cannot afford a 50-frame classifier warmup - every player would fall back
        # to "team_a" for a large slice of the video. Scale it to the clip length. A tenth is
        # ample: each frame contributes one colour sample per player, so even 5 frames clears
        # the 10-sample minimum that fit() needs.
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if total_frames and total_frames > 0:
            self.classifier.warmup_frames = max(5, min(50, int(total_frames // 10)))

        batch = []
        frame_num = 0

        # Class IDs mapping from our YOLO model
        # 0: ball, 1: goalkeeper, 2: player, 3: referee

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # Track camera shift
            dx, dy = self.camera_tracker.update(frame)

            # YOLOv8 Predict
            results = self.model.predict(frame, conf=0.1, verbose=False, device=self.device)[0]
            cls_names = results.names
            cls_names_inv = {v: k for k, v in cls_names.items()}

            detections = sv.Detections.from_ultralytics(results)

            # Map Goalkeepers to Players for the ByteTrack system
            for idx, class_id in enumerate(detections.class_id):
                if cls_names[class_id] == "goalkeeper":
                    detections.class_id[idx] = cls_names_inv["player"]

            # Update Tracker (ByteTrack)
            tracked_detections = self.tracker.update_with_detections(detections)

            # Collect player bounding boxes to feed the team classifier warmup
            player_bboxes = []
            for frame_detection in tracked_detections:
                bbox = frame_detection[0].tolist()
                class_id = frame_detection[3]
                if class_id == cls_names_inv["player"]:
                    player_bboxes.append(bbox)

            # Process jersey colors for team classification
            self.classifier.process_frame_detections(frame, player_bboxes)

            # 1. Process Tracked Players and Referees
            for frame_detection in tracked_detections:
                bbox = frame_detection[0].tolist()
                class_id = frame_detection[3]
                track_id = int(frame_detection[4])

                # Foot position is the center bottom of bounding box
                foot_x, foot_y = get_foot_position(bbox)

                # Apply camera offset
                foot_x_adj = foot_x - dx
                foot_y_adj = foot_y - dy

                # Project to Pitch
                pitch_x, pitch_y = self.project_point(H, foot_x_adj, foot_y_adj)

                # Classify
                if class_id == cls_names_inv["player"]:
                    # Check manual overrides for goalkeepers or custom IDs first
                    if track_id in gk_overrides:
                        team = gk_overrides[track_id]
                    else:
                        team = self.classifier.get_player_team(frame, bbox, track_id)
                elif class_id == cls_names_inv["referee"]:
                    team = "referee"
                else:
                    continue

                record = {
                    "frame_number": frame_num,
                    "player_id": track_id,
                    "team_classification": team,
                    "x_pixel": float(foot_x),
                    "y_pixel": float(foot_y),
                    "x_pitch": float(pitch_x),
                    "y_pitch": float(pitch_y),
                }
                batch.append(record)

                if len(batch) >= 500:
                    yield batch
                    batch = []

            # 2. Process Untracked Ball
            for frame_detection in detections:
                bbox = frame_detection[0].tolist()
                class_id = frame_detection[3]

                if class_id == cls_names_inv["ball"]:
                    ball_x, ball_y = get_center_of_bbox(bbox)

                    # Apply camera offset
                    ball_x_adj = ball_x - dx
                    ball_y_adj = ball_y - dy

                    pitch_x, pitch_y = self.project_point(H, ball_x_adj, ball_y_adj)

                    record = {
                        "frame_number": frame_num,
                        "player_id": -1,  # ID -1 reserved for the ball
                        "team_classification": "ball",
                        "x_pixel": float(ball_x),
                        "y_pixel": float(ball_y),
                        "x_pitch": float(pitch_x),
                        "y_pitch": float(pitch_y),
                    }
                    batch.append(record)

                    if len(batch) >= 500:
                        yield batch
                        batch = []

            frame_num += 1

        cap.release()

        # Yield any remaining coordinates
        if batch:
            yield batch
