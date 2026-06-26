from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Match, TrackingCoordinate
from .serializers import MatchSerializer, MatchCreateSerializer, MatchStatusSerializer

class MatchListCreateView(generics.ListCreateAPIView):
    def get_queryset(self):
        # Users must only see their own matches
        return Match.objects.filter(owner=self.request.user).order_by("-created_at")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MatchCreateSerializer
        return MatchSerializer


class MatchDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = MatchSerializer

    def get_queryset(self):
        # Filter by owner ensures a 404 is returned if the match is not owned by the user
        return Match.objects.filter(owner=self.request.user)


class MatchStatusView(generics.RetrieveAPIView):
    serializer_class = MatchStatusSerializer

    def get_queryset(self):
        return Match.objects.filter(owner=self.request.user)


class MatchFramesView(APIView):
    def get(self, request, pk):
        # Check ownership and return 404 if not found/not owned
        match = get_object_or_404(Match, pk=pk, owner=request.user)
        
        try:
            frame_start = int(request.query_params.get("frame_start", 0))
            frame_end = int(request.query_params.get("frame_end", 750))
        except ValueError:
            return Response(
                {"error": "frame_start and frame_end must be integers."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if frame_start < 0 or frame_end < 0:
            return Response(
                {"error": "frame parameters must be positive integers."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if frame_end - frame_start > 1500:
            return Response(
                {"error": "Cannot request more than 1500 frames at a time."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Retrieve coordinates within the specified frame window
        coords = TrackingCoordinate.objects.filter(
            match=match,
            frame_number__gte=frame_start,
            frame_number__lte=frame_end
        ).order_by("frame_number")
        
        # Structure the response: {frame_number: [{player_id, team, x, y}, ...]}
        data = {}
        for coord in coords:
            fn = coord.frame_number
            if fn not in data:
                data[fn] = []
            data[fn].append({
                "player_id": coord.player_id,
                "team": coord.team_classification,
                "x": coord.x_coord,
                "y": coord.y_coord
            })
            
        return Response(data)
