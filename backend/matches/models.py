from django.db import models
from django.conf import settings
import uuid

def match_video_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    unique_id = uuid.uuid4()
    return f"uploads/matches/{instance.owner.id}/{unique_id}/video.{ext}"

class Match(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="matches")
    title = models.CharField(max_length=255)
    video_file = models.FileField(upload_to=match_video_upload_path)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    calibration_matrix = models.JSONField(null=True, blank=True)
    error_log = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} ({self.status})"

class TrackingCoordinate(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="coordinates")
    frame_number = models.IntegerField()
    player_id = models.IntegerField()
    team_classification = models.CharField(max_length=20)
    x_coord = models.FloatField()
    y_coord = models.FloatField()

    class Meta:
        indexes = [
            models.Index(fields=["match", "frame_number"]),
            models.Index(fields=["match", "player_id"]),
        ]

    def __str__(self):
        return f"Match {self.match_id} | Frame {self.frame_number} | Player {self.player_id} ({self.team_classification})"

class MatchEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ("possession", "Possession Change"),
        ("pass", "Pass"),
        ("interception", "Interception"),
        ("shot", "Shot"),
        ("sprint", "Sprint"),
    ]

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    frame_number = models.IntegerField()
    player_initiator = models.IntegerField(null=True, blank=True)
    player_receiver = models.IntegerField(null=True, blank=True)
    team = models.CharField(max_length=20, null=True, blank=True)
    x_coord = models.FloatField(null=True, blank=True)
    y_coord = models.FloatField(null=True, blank=True)
    details = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["match", "event_type"]),
            models.Index(fields=["match", "frame_number"]),
        ]

    def __str__(self):
        return f"Match {self.match_id} | Frame {self.frame_number} | {self.event_type} ({self.team})"
