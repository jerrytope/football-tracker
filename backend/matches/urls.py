from django.urls import path
from .views import MatchListCreateView, MatchDetailView, MatchStatusView, MatchFramesView, MatchEventsView

urlpatterns = [
    path("", MatchListCreateView.as_view(), name="match_list_create"),
    path("<int:pk>/", MatchDetailView.as_view(), name="match_detail"),
    path("<int:pk>/status/", MatchStatusView.as_view(), name="match_status"),
    path("<int:pk>/frames/", MatchFramesView.as_view(), name="match_frames"),
    path("<int:pk>/events/", MatchEventsView.as_view(), name="match_events"),
]
