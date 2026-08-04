from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.organizations.views import (
    InvitationAcceptView,
    InvitationPublicDetailView,
    InvitationViewSet,
    MembershipViewSet,
    SetupView,
)

router = SimpleRouter(trailing_slash=True)
router.register("members", MembershipViewSet, basename="membership")
router.register("invitations", InvitationViewSet, basename="invitation")

urlpatterns = [
    path("setup/", SetupView.as_view(), name="setup"),
    *router.urls,
    path(
        "invitations/<str:token>/",
        InvitationPublicDetailView.as_view(),
        name="invitation-public-detail",
    ),
    path(
        "invitations/<str:token>/accept/",
        InvitationAcceptView.as_view(),
        name="invitation-accept",
    ),
]
