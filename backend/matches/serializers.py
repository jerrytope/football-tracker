from rest_framework import serializers
from .models import Match, TrackingCoordinate, MatchEvent

class TrackingCoordinateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackingCoordinate
        fields = ("frame_number", "player_id", "team_classification", "x_coord", "y_coord")

class MatchSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    total_frames = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = (
            "id",
            "owner",
            "title",
            "video_file",
            "status",
            "calibration_matrix",
            "video_fps",
            "error_log",
            "created_at",
            "updated_at",
            "processing_started_at",
            "processing_completed_at",
            "total_frames",
        )
        read_only_fields = (
            "owner",
            "status",
            "calibration_matrix",
            "video_fps",
            "error_log",
            "processing_started_at",
            "processing_completed_at",
            "total_frames",
        )

    def get_total_frames(self, obj):
        from django.db.models import Max
        max_frame = obj.coordinates.aggregate(Max('frame_number'))['frame_number__max']
        return max_frame if max_frame is not None else 0

class MatchCreateSerializer(serializers.ModelSerializer):
    # Optional at upload time. Supply a config produced by cv_engine/engine/calibrate.py to
    # pin the pitch homography for this clip's camera position. Omitted, the task falls back
    # to settings.DEFAULT_CALIBRATION_PATH, then to a generic rescaled trapezoid.
    calibration_matrix = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = Match
        fields = ("id", "title", "video_file", "calibration_matrix")

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
