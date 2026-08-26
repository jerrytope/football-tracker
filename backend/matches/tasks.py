import os
import traceback
import tempfile
import json
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from .models import Match, TrackingCoordinate
from .utils import weights_manager
from cv_engine.engine.extractor import CoordinatesExtractor

@shared_task(bind=True, queue="gpu", max_retries=1)
def process_match_video(self, match_id):
    """
    Asynchronous task to process a match video file, extract player and ball
    coordinates, and bulk insert them into the TrackingCoordinate table.
    """
    try:
        match = Match.objects.get(pk=match_id)
    except Match.DoesNotExist:
        # Match was deleted before processing started
        return f"Match {match_id} does not exist."

    # Update status to processing
    match.status = "processing"
    match.processing_started_at = timezone.now()
    match.save(update_fields=["status", "processing_started_at"])

    video_path = None
    is_temp_video = False

    try:
        # 1. Resolve video path (S3 file or local path)
        if settings.USE_S3:
            # Download file from S3 to a local temp file for OpenCV
            suffix = os.path.splitext(match.video_file.name)[-1]
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            video_path = temp_file.name
            temp_file.close()

            # Download using file storage system (Django-storages wrapper)
            with match.video_file.open("rb") as s3_file:
                with open(video_path, "wb") as local_file:
                    # Read and write in chunks to avoid memory issues
                    for chunk in s3_file.chunks():
                        local_file.write(chunk)
            is_temp_video = True
        else:
            video_path = match.video_file.path

        # 2. Get local weights path (using weights_manager)
        weights_path = weights_manager.get_weights_path()

        # 3. Instantiate Coordinates Extractor and run pipeline
        extractor = CoordinatesExtractor(model_path=weights_path)

        # 3b. Resolve the calibration. Uploads through the UI carry none, and the extractor's
        #     fallback is a generic trapezoid that does not match most camera angles - it lands
        #     the centre circle around y=50 instead of y=34. A configured default is far better
        #     than that guess for footage from a known camera position.
        calibration_config = match.calibration_matrix
        if not calibration_config and settings.DEFAULT_CALIBRATION_PATH:
            default_path = settings.DEFAULT_CALIBRATION_PATH
            if not os.path.isabs(default_path):
                default_path = os.path.abspath(
                    os.path.join(settings.BASE_DIR.parent, default_path)
                )
            if os.path.exists(default_path):
                with open(default_path) as calib_file:
                    calibration_config = json.load(calib_file)
                print(f"[Task] Using default calibration from {default_path}")
            else:
                print(f"[Task] DEFAULT_CALIBRATION_PATH set but not found: {default_path}")

        # 4. Extract coordinates in batches of 500 frames
        coordinate_generator = extractor.extract_coordinates(
            video_path=video_path,
            calibration_config=calibration_config
        )

        for batch in coordinate_generator:
            coords_to_create = []
            for record in batch:
                coords_to_create.append(
                    TrackingCoordinate(
                        match=match,
                        frame_number=record["frame_number"],
                        player_id=record["player_id"],
                        team_classification=record["team_classification"],
                        x_coord=record["x_pitch"],
                        y_coord=record["y_pitch"]
                    )
                )
            # Perform bulk insert
            TrackingCoordinate.objects.bulk_create(coords_to_create, batch_size=10000)

        # 5. Record the frame rate read off the video, and store the homography that was
        #    actually used for this clip (which may have been rescaled to its resolution).
        match.video_fps = extractor.video_fps

        if not match.calibration_matrix:
            match.calibration_matrix = {
                "homography_matrix": extractor.active_H.tolist()
            }

        # 5b. Extract tactical events from raw coordinates
        from .utils.event_extractor import extract_match_events
        extract_match_events(match.id, fps=match.video_fps)

        # 6. Mark match as completed
        match.status = "completed"
        match.processing_completed_at = timezone.now()
        match.save(update_fields=[
            "status", "processing_completed_at", "calibration_matrix", "video_fps"
        ])

        return f"Match {match_id} processed successfully."

    except Exception as e:
        # On failure, log the traceback and mark status as failed
        error_info = traceback.format_exc()
        match.status = "failed"
        match.error_log = error_info
        match.save(update_fields=["status", "error_log"])
        
        # Re-raise the exception to allow Celery to track the failure
        raise e

    finally:
        # 7. Clean up temporary video file if created
        if is_temp_video and video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except Exception as cleanup_error:
                # Log cleanup warning but do not crash task
                print(f"Warning: Failed to delete temp video file at {video_path}: {cleanup_error}")
