import cv2
import numpy as np
from sklearn.cluster import KMeans

class TeamClassifier:
    def __init__(self, warmup_frames=50):
        self.warmup_frames = warmup_frames
        self.frame_count = 0
        self.player_colors = []
        self.kmeans = None
        self.team_colors = {}
        self.player_team_cache = {}

    def get_player_color(self, frame, bbox):
        """
        Extract the top-60% of the bounding box (jersey region) and calculate the mean color.
        """
        x1, y1, x2, y2 = map(int, bbox)
        
        # Ensure coordinates are within frame boundaries
        h, w, _ = frame.shape
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        
        if (x2 - x1) <= 0 or (y2 - y1) <= 0:
            return np.array([0.0, 0.0, 0.0])

        crop = frame[y1:y2, x1:x2]
        
        # Extract jersey region (top 60% of the box height)
        jersey_height = int((y2 - y1) * 0.6)
        if jersey_height <= 0:
            return np.array([0.0, 0.0, 0.0])
            
        jersey_crop = crop[0:jersey_height, :]
        
        # Calculate mean color (OpenCV loads as BGR, we'll keep BGR)
        mean_color = cv2.mean(jersey_crop)[:3]
        return np.array(mean_color)

    def process_frame_detections(self, frame, player_bboxes):
        """
        Collect player colors during the warmup phase.
        """
        if self.kmeans is not None:
            return

        self.frame_count += 1
        for bbox in player_bboxes:
            color = self.get_player_color(frame, bbox)
            if not np.all(color == 0.0):
                self.player_colors.append(color)

        # Fit K-Means once we have collected enough samples after warmup_frames
        if self.frame_count >= self.warmup_frames and len(self.player_colors) >= 10:
            self.fit()

    def fit(self):
        """
        Fit K-Means (K=2) on collected player colors.
        """
        if len(self.player_colors) < 2:
            return
            
        # Run KMeans with 2 clusters (for the two teams)
        self.kmeans = KMeans(n_clusters=2, init="k-means++", n_init=10, random_state=42)
        self.kmeans.fit(self.player_colors)
        
        # Store team dominant colors
        self.team_colors[0] = self.kmeans.cluster_centers_[0]
        self.team_colors[1] = self.kmeans.cluster_centers_[1]
        print(f"[Classifier] Fitted KMeans on {len(self.player_colors)} player colors successfully.")

    def get_player_team(self, frame, bbox, player_id):
        """
        Get the team classification ('team_a' or 'team_b') for a player.
        """
        # If player_id is already classified, return the cached classification
        if player_id in self.player_team_cache:
            return self.player_team_cache[player_id]

        # If KMeans is not fitted yet, default to 'team_a' temporarily
        if self.kmeans is None:
            # Check if we have enough samples to fit right away if warmup is done
            if len(self.player_colors) >= 2:
                self.fit()
            if self.kmeans is None:
                return "team_a"

        color = self.get_player_color(frame, bbox)
        if np.all(color == 0.0):
            return "team_a"

        # Predict cluster label (0 or 1)
        cluster_id = self.kmeans.predict(color.reshape(1, -1))[0]
        team = "team_a" if cluster_id == 0 else "team_b"
        
        # Cache the team for this player_id to maintain consistency
        self.player_team_cache[player_id] = team
        return team
