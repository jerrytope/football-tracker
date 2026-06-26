from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch
from .models import Match, TrackingCoordinate, MatchEvent
from .utils.event_extractor import extract_match_events

User = get_user_model()

class MatchAPITests(APITestCase):
    def setUp(self):
        # Create users
        self.user1 = User.objects.create_user(username="user1", password="password123")
        self.user2 = User.objects.create_user(username="user2", password="password123")

        # Credentials
        self.client.force_authenticate(user=self.user1)

        # Create a mock video file
        self.mock_video = SimpleUploadedFile(
            name="test_video.mp4",
            content=b"dummy video content",
            content_type="video/mp4"
        )

        # Base URLs
        self.list_create_url = reverse("match_list_create")

    @patch("matches.tasks.process_match_video.apply_async")
    def test_create_match(self, mock_apply_async):
        data = {
            "title": "Match A vs Match B",
            "video_file": self.mock_video
        }
        response = self.client.post(self.list_create_url, data, format="multipart")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Match.objects.count(), 1)
        
        match = Match.objects.first()
        self.assertEqual(match.owner, self.user1)
        self.assertEqual(match.title, "Match A vs Match B")
        self.assertEqual(match.status, "pending")
        
        # Verify Celery task was triggered
        mock_apply_async.assert_called_once_with(args=[match.id], queue="gpu")

    def test_list_matches_isolation(self):
        # Match owned by user1
        match1 = Match.objects.create(owner=self.user1, title="Match 1", video_file=self.mock_video)
        # Match owned by user2
        match2 = Match.objects.create(owner=self.user2, title="Match 2", video_file=self.mock_video)

        # Query matches as user1
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], match1.id)

    def test_retrieve_match_details(self):
        match = Match.objects.create(owner=self.user1, title="My Match", video_file=self.mock_video)
        detail_url = reverse("match_detail", kwargs={"pk": match.id})

        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "My Match")

    def test_retrieve_match_details_not_owner_returns_404(self):
        # Match owned by user2
        match = Match.objects.create(owner=self.user2, title="Someone Else's Match", video_file=self.mock_video)
        detail_url = reverse("match_detail", kwargs={"pk": match.id})

        # Query as user1
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_match_cascades_to_coordinates(self):
        match = Match.objects.create(owner=self.user1, title="My Match", video_file=self.mock_video)
        TrackingCoordinate.objects.create(
            match=match, frame_number=1, player_id=10, team_classification="home", x_coord=10.5, y_coord=20.5
        )
        self.assertEqual(TrackingCoordinate.objects.count(), 1)

        detail_url = reverse("match_detail", kwargs={"pk": match.id})
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Match.objects.count(), 0)
        self.assertEqual(TrackingCoordinate.objects.count(), 0)

    def test_match_status_endpoint(self):
        match = Match.objects.create(
            owner=self.user1, 
            title="Processing Match", 
            video_file=self.mock_video,
            status="processing"
        )
        status_url = reverse("match_status", kwargs={"pk": match.id})

        response = self.client.get(status_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "processing")
        self.assertIn("error_log", response.data)

    def test_match_frames_coordinate_endpoint(self):
        match = Match.objects.create(owner=self.user1, title="Match Frames", video_file=self.mock_video)
        
        # Create dummy coordinates
        TrackingCoordinate.objects.create(
            match=match, frame_number=0, player_id=1, team_classification="home", x_coord=5.0, y_coord=10.0
        )
        TrackingCoordinate.objects.create(
            match=match, frame_number=0, player_id=2, team_classification="away", x_coord=15.0, y_coord=20.0
        )
        TrackingCoordinate.objects.create(
            match=match, frame_number=1, player_id=-1, team_classification="ball", x_coord=25.0, y_coord=30.0
        )

        frames_url = reverse("match_frames", kwargs={"pk": match.id})
        
        # Query frame 0 to 1
        response = self.client.get(frames_url, {"frame_start": 0, "frame_end": 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Validate structure: {frame_number: [{player_id, team, x, y}, ...]}
        json_data = response.json()
        self.assertIn("0", json_data)
        self.assertIn("1", json_data)
        self.assertEqual(len(json_data["0"]), 2)
        self.assertEqual(len(json_data["1"]), 1)
        
        player1 = json_data["0"][0]
        self.assertEqual(player1["player_id"], 1)
        self.assertEqual(player1["team"], "home")
        self.assertEqual(player1["x"], 5.0)
        self.assertEqual(player1["y"], 10.0)

    def test_match_frames_pagination_limit(self):
        match = Match.objects.create(owner=self.user1, title="Match Limit Check", video_file=self.mock_video)
        frames_url = reverse("match_frames", kwargs={"pk": match.id})

        # Request 1600 frames (> 1500)
        response = self.client.get(frames_url, {"frame_start": 0, "frame_end": 1600})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_retrieve_events_endpoint_isolation(self):
        match1 = Match.objects.create(owner=self.user1, title="My Match", video_file=self.mock_video)
        match2 = Match.objects.create(owner=self.user2, title="Other Match", video_file=self.mock_video)
        
        MatchEvent.objects.create(match=match2, event_type="shot", frame_number=5, team="away")
        
        events_url = reverse("match_events", kwargs={"pk": match2.id})
        response = self.client.get(events_url)
        # Should return 404 since it's not owned by user1
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_events_endpoint_filters(self):
        match = Match.objects.create(owner=self.user1, title="Events Filter Match", video_file=self.mock_video)
        MatchEvent.objects.create(match=match, event_type="pass", frame_number=5, team="home")
        MatchEvent.objects.create(match=match, event_type="shot", frame_number=10, team="home")
        
        events_url = reverse("match_events", kwargs={"pk": match.id})
        
        # Filter for pass events only
        response = self.client.get(events_url, {"event_type": "pass"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["event_type"], "pass")

    def test_event_extractor_possession_and_pass(self):
        match = Match.objects.create(owner=self.user1, title="Extractor Test", video_file=self.mock_video)
        
        # Frame 0: Ball is close to Player 1 (home) -> possession established
        TrackingCoordinate.objects.create(match=match, frame_number=0, player_id=-1, team_classification="ball", x_coord=50.0, y_coord=30.0)
        TrackingCoordinate.objects.create(match=match, frame_number=0, player_id=1, team_classification="home", x_coord=50.5, y_coord=30.0)
        
        # Frame 1: Ball is free but within timeout
        TrackingCoordinate.objects.create(match=match, frame_number=1, player_id=-1, team_classification="ball", x_coord=52.0, y_coord=32.0)
        
        # Frame 2: Ball is close to Player 2 (home) -> successful pass
        TrackingCoordinate.objects.create(match=match, frame_number=2, player_id=-1, team_classification="ball", x_coord=55.0, y_coord=35.0)
        TrackingCoordinate.objects.create(match=match, frame_number=2, player_id=2, team_classification="home", x_coord=55.5, y_coord=35.0)
        
        # Run extractor
        result = extract_match_events(match.id, fps=20)
        self.assertIn("Successfully extracted", result)
        
        # Check possession events
        possession_events = MatchEvent.objects.filter(match=match, event_type="possession")
        self.assertEqual(possession_events.count(), 1)
        self.assertEqual(possession_events.first().player_initiator, 1)
        
        # Check pass events
        pass_events = MatchEvent.objects.filter(match=match, event_type="pass")
        self.assertEqual(pass_events.count(), 1)
        self.assertEqual(pass_events.first().player_initiator, 1)
        self.assertEqual(pass_events.first().player_receiver, 2)
        self.assertEqual(pass_events.first().details["success"], True)

    def test_event_extractor_interception(self):
        match = Match.objects.create(owner=self.user1, title="Interception Extractor Test", video_file=self.mock_video)
        
        # Frame 0: Ball close to Player 1 (home)
        TrackingCoordinate.objects.create(match=match, frame_number=0, player_id=-1, team_classification="ball", x_coord=50.0, y_coord=30.0)
        TrackingCoordinate.objects.create(match=match, frame_number=0, player_id=1, team_classification="home", x_coord=50.5, y_coord=30.0)
        
        # Frame 1: Ball close to Player 3 (away) -> intercepted
        TrackingCoordinate.objects.create(match=match, frame_number=1, player_id=-1, team_classification="ball", x_coord=55.0, y_coord=35.0)
        TrackingCoordinate.objects.create(match=match, frame_number=1, player_id=3, team_classification="away", x_coord=55.5, y_coord=35.0)
        
        extract_match_events(match.id, fps=20)
        
        # Verify interception event
        interceptions = MatchEvent.objects.filter(match=match, event_type="interception")
        self.assertEqual(interceptions.count(), 1)
        self.assertEqual(interceptions.first().player_initiator, 1)
        self.assertEqual(interceptions.first().player_receiver, 3)
        self.assertEqual(interceptions.first().team, "away")
        
        # Verify failed pass event
        failed_passes = MatchEvent.objects.filter(match=match, event_type="pass", details={"success": False})
        self.assertEqual(failed_passes.count(), 1)
        self.assertEqual(failed_passes.first().player_initiator, 1)

    def test_event_extractor_shot(self):
        match = Match.objects.create(owner=self.user1, title="Shot Extractor Test", video_file=self.mock_video)
        
        # Frame 0: Ball close to Player 1 (home) at (10, 34)
        TrackingCoordinate.objects.create(match=match, frame_number=0, player_id=-1, team_classification="ball", x_coord=10.0, y_coord=34.0)
        TrackingCoordinate.objects.create(match=match, frame_number=0, player_id=1, team_classification="home", x_coord=10.2, y_coord=34.0)
        
        # Frame 1: Ball shot leftwards with high speed towards target X=0, Y=34 (goal mouth)
        # Distance = 2.0 meters. Speed = 2.0 * 20 = 40.0 m/s.
        TrackingCoordinate.objects.create(match=match, frame_number=1, player_id=-1, team_classification="ball", x_coord=8.0, y_coord=34.0)
        
        extract_match_events(match.id, fps=20)
        
        # Verify shot event
        shots = MatchEvent.objects.filter(match=match, event_type="shot")
        self.assertEqual(shots.count(), 1)
        self.assertEqual(shots.first().player_initiator, 1)
        self.assertEqual(shots.first().team, "home")
        self.assertEqual(shots.first().details["target_goal"], "left")
        self.assertGreater(shots.first().details["speed_ms"], 18.0)
