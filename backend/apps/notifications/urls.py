from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.notifications.views import (
    NotificationPreferenceDetailView,
    NotificationPreferenceListView,
    NotificationViewSet,
)

router = SimpleRouter(trailing_slash=True)
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    # Explicit paths ahead of the router — mirrors apps.bugs.urls's identical
    # convention for nested/nonstandard routes living outside the router.
    path(
        "notifications/preferences/",
        NotificationPreferenceListView.as_view(),
        name="notification-preference-list",
    ),
    path(
        "notifications/preferences/<str:event_type>/",
        NotificationPreferenceDetailView.as_view(),
        name="notification-preference-detail",
    ),
] + router.urls
