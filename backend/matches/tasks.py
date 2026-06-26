import os
import traceback
import tempfile
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
        
        # 4. Extract coordinates in batches of 500 frames
        coordinate_generator = extractor.extract_coordinates(
            video_path=video_path,
            calibration_config=match.calibration_matrix
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

        # 5. Store final calibration matrix if not already stored
        if not match.calibration_matrix:
            match.calibration_matrix = {
                "homography_matrix": extractor.default_H.tolist()
            }

        # 5b. Extract tactical events from raw coordinates
        from .utils.event_extractor import extract_match_events
        extract_match_events(match.id)

        # 6. Mark match as completed
        match.status = "completed"
        match.processing_completed_at = timezone.now()
        match.save(update_fields=["status", "processing_completed_at", "calibration_matrix"])

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
