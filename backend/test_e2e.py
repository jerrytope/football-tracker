import os
import json
import sys
import time
import django

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.core.files import File
from matches.models import Match, TrackingCoordinate

User = get_user_model()

def run_test():
    print("--- Starting End-to-End Integration Test ---")
    
    # 1. Clean old test data if exists
    User.objects.filter(username="e2e_test_user").delete()
    
    # 2. Create e2e test user
    user = User.objects.create_user(username="e2e_test_user", password="e2epassword123")
    print(f"Created e2e test user: {user.username}")
    
    # 3. Resolve test video path.
    #    Defaults to the short smoke-test clip; pass a filename (or a full path) as argv[1]
    #    to run against something else, e.g. `python test_e2e.py test_5s.mp4`.
    clip = sys.argv[1] if len(sys.argv) > 1 else "clip_3min.mp4"
    if os.path.isabs(clip):
        video_path = clip
    else:
        video_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "cv_engine", "test_data", clip)
        )
    if not os.path.exists(video_path):
        print(f"Error: test video not found at {video_path}")
        return
        
    print(f"Found test video at {video_path} ({os.path.getsize(video_path)} bytes)")
    
    # 3b. Optional calibration config (argv[2]), produced by cv_engine/engine/calibrate.py.
    #     Without one the extractor falls back to a generic trapezoid rescaled to the clip's
    #     resolution, which is a guess at the camera angle rather than a measurement of it.
    calibration = None
    if len(sys.argv) > 2:
        calib_path = sys.argv[2]
        if not os.path.isabs(calib_path):
            calib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", calib_path))
        if not os.path.exists(calib_path):
            print(f"Error: calibration config not found at {calib_path}")
            return
        with open(calib_path) as cf:
            calibration = json.load(cf)
        print(f"Using calibration from {calib_path}")

    # 4. Create Match (this will upload/copy the file to media/)
    with open(video_path, "rb") as f:
        match = Match.objects.create(
            owner=user,
            title="E2E Test Match",
            video_file=File(f, name=os.path.basename(video_path)),
            calibration_matrix=calibration
        )
    print(f"Created Match {match.id}. Initial Status: {match.status}")
    
    # Trigger task manually to make sure it runs (normally done by serializer, 
    # but since we bypass the serializer here, we invoke it directly)
    from matches.tasks import process_match_video
    print("Triggering Celery task process_match_video...")
    process_match_video.apply_async(args=[match.id], queue="gpu")
    
    # 5. Poll status
    start_time = time.time()
    max_timeout = 3600  # 3 minutes max
    
    print("Polling match status...")
    while time.time() - start_time < max_timeout:
        match.refresh_from_db()
        print(f"[{int(time.time() - start_time)}s] Match status: {match.status}")
        
        if match.status in ["completed", "failed"]:
            break
        time.sleep(5)
        
    if match.status == "completed":
        coord_count = TrackingCoordinate.objects.filter(match=match).count()
        print(f"Success! Match processing completed successfully in {int(time.time() - start_time)}s.")
        print(f"Total TrackingCoordinates saved: {coord_count}")
        
        # Verify coordinates exist per frame
        frames = TrackingCoordinate.objects.filter(match=match).values_list("frame_number", flat=True).distinct()
        print(f"Unique frames with tracking data: {len(frames)}")

        # Sanity-check the projection: a green run proves the pipeline ran, not that the
        # homography suited this footage. If the spread pins to the pitch boundaries, the
        # clipping in project_point() is saturating and the matrix is wrong for this clip.
        from django.db.models import Min, Max
        spread = TrackingCoordinate.objects.filter(match=match).aggregate(
            Min("x_coord"), Max("x_coord"), Min("y_coord"), Max("y_coord")
        )
        print(f"Detected fps: {match.video_fps}")
        print(
            "Pitch coordinate spread: "
            f"x {spread['x_coord__min']:.1f}-{spread['x_coord__max']:.1f} (of 0-105), "
            f"y {spread['y_coord__min']:.1f}-{spread['y_coord__max']:.1f} (of 0-68)"
        )

        teams = sorted(
            TrackingCoordinate.objects.filter(match=match)
            .values_list("team_classification", flat=True)
            .distinct()
        )
        ball_rows = TrackingCoordinate.objects.filter(match=match, player_id=-1).count()
        print(f"Team classifications present: {teams}")
        print(f"Ball rows (player_id=-1): {ball_rows}")
        if ball_rows == 0:
            print("WARNING: no ball detected - possession, pass and shot events cannot fire.")
        
        # Verify and print extracted events
        from matches.models import MatchEvent
        events = MatchEvent.objects.filter(match=match).order_by("frame_number")
        print(f"Total MatchEvents saved: {events.count()}")
        for event in events:
            print(f"  Frame {event.frame_number}: {event.event_type} | Team: {event.team} | Init: {event.player_initiator} | Recv: {event.player_receiver} | Details: {event.details}")
            
        if coord_count > 0 and events.count() > 0:
            print("E2E Test PASSED!")
        else:
            print(f"E2E Test FAILED: Coordinates = {coord_count}, Events = {events.count()}")
    else:
        print(f"E2E Test FAILED. Match status: {match.status}")
        if match.error_log:
            print(f"Error Log:\n{match.error_log}")
            
if __name__ == "__main__":
    run_test()
