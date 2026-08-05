from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.bugs.views import BugRelationshipDetailView, BugTagDetailView, BugViewSet

router = SimpleRouter(trailing_slash=True)
router.register("bugs", BugViewSet, basename="bug")

urlpatterns = [
    # Explicit nested DELETE routes — see the comment in views.py above
    # BugTagDetailView for why these aren't router-generated @actions.
    path("bugs/<uuid:pk>/tags/<uuid:tag_id>/", BugTagDetailView.as_view(), name="bug-tag-detail"),
    path(
        "bugs/<uuid:pk>/relationships/<uuid:relationship_id>/",
        BugRelationshipDetailView.as_view(),
        name="bug-relationship-detail",
    ),
] + router.urls
