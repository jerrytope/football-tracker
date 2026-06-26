from rest_framework import serializers
from .models import Match, TrackingCoordinate, MatchEvent

class TrackingCoordinateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackingCoordinate
        fields = ("frame_number", "player_id", "team_classification", "x_coord", "y_coord")

class MatchSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Match
        fields = (
            "id",
            "owner",
            "title",
            "video_file",
            "status",
            "calibration_matrix",
            "error_log",
            "created_at",
            "updated_at",
            "processing_started_at",
            "processing_completed_at",
        )
        read_only_fields = (
            "owner",
            "status",
            "calibration_matrix",
            "error_log",
            "processing_started_at",
            "processing_completed_at",
        )

class MatchCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Match
        fields = ("id", "title", "video_file")

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user:
            validated_data["owner"] = request.user
        match = super().create(validated_data)
        
        # Trigger Celery task (lazy-loaded to avoid circular imports)
        from .tasks import process_match_video
        process_match_video.apply_async(args=[match.id], queue="gpu")
        
        return match

class MatchStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Match
        fields = ("status", "processing_started_at", "processing_completed_at", "error_log")

class MatchEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = MatchEvent
        fields = (
            "id",
            "event_type",
            "frame_number",
            "player_initiator",
            "player_receiver",
            "team",
            "x_coord",
            "y_coord",
            "details",
        )
