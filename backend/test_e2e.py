import os
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
    
    # 3. Resolve test video path
    video_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "cv_engine", "test_data", "clip_3min.mp4")
    )
    if not os.path.exists(video_path):
        print(f"Error: test video not found at {video_path}")
        return
        
    print(f"Found test video at {video_path} ({os.path.getsize(video_path)} bytes)")
    
    # 4. Create Match (this will upload/copy the file to media/)
    with open(video_path, "rb") as f:
        match = Match.objects.create(
            owner=user,
            title="E2E Test Match",
            video_file=File(f, name="clip_3min.mp4")
        )
    print(f"Created Match {match.id}. Initial Status: {match.status}")
    
    # Trigger task manually to make sure it runs (normally done by serializer, 
    # but since we bypass the serializer here, we invoke it directly)
    from matches.tasks import process_match_video
    print("Triggering Celery task process_match_video...")
    process_match_video.apply_async(args=[match.id], queue="gpu")
    
    # 5. Poll status
    start_time = time.time()
    max_timeout = 180  # 3 minutes max
    
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
