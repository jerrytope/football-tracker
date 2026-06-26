from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch
from .models import Match, TrackingCoordinate

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
