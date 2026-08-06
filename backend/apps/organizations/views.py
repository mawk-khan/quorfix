from django.conf import settings
from django.contrib.auth import login
from django.core.mail import send_mail
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from apps.organizations.permissions import IsOrganizationAdministrator, IsOrganizationMember
from apps.organizations.selectors import get_organization_members, get_pending_invitations
from apps.organizations.serializers import (
    InvitationAcceptSerializer,
    InvitationCreateSerializer,
    InvitationPublicDetailSerializer,
    InvitationSerializer,
    MembershipRoleUpdateSerializer,
    MembershipSerializer,
    SessionSerializer,
    SetupSerializer,
)
from apps.organizations.services import (
    InvitationAlreadyPending,
    InvitationInvalid,
    LastAdministratorError,
    MemberAlreadyExists,
    SetupAlreadyCompleted,
    SetupNotAllowed,
    accept_invitation,
    change_member_role,
    create_invitation,
    get_invitation_by_token,
    is_instance_configured,
    remove_member,
    revoke_invitation,
    setup_instance,
)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionView(APIView):
    """Reports the caller's auth state and, as a side effect, seeds the CSRF
    cookie. The frontend calls this unconditionally on every route load —
    including public pages like /setup and /invitations/[token] — since
    those pages' forms need a CSRF cookie to submit at all.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        membership = getattr(request, "membership", None) if user else None
        organization = getattr(request, "organization", None) if user else None

        data = {
            "authenticated": user is not None,
            "user": user,
            "organization": organization,
            "role": membership.role if membership else None,
        }
        return Response(SessionSerializer(data).data)


@method_decorator(csrf_protect, name="dispatch")
class SetupView(APIView):
    """First-run instance setup: creates the admin user + the one organization.

    CSRF-protected explicitly for the same reason as LoginView — this is an
    anonymous POST that SessionAuthentication's CSRF enforcement never sees.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get_throttles(self):
        # GET is a cheap, frequently-polled status check (every /setup page
        # load); POST is the sensitive, meant-to-run-once action. Sharing one
        # scope would let ordinary page loads exhaust the quota meant to
        # rate-limit the POST.
        self.throttle_scope = "setup-status" if self.request.method == "GET" else "setup"
        return super().get_throttles()

    def get(self, request):
        return Response({"is_configured": is_instance_configured()})

    def post(self, request):
        serializer = SetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user, _organization, _membership = setup_instance(
                organization_name=serializer.validated_data["organization_name"],
                email=serializer.validated_data["email"],
                password=serializer.validated_data["password"],
                first_name=serializer.validated_data["first_name"],
                last_name=serializer.validated_data["last_name"],
            )
        except SetupAlreadyCompleted:
            return Response(
                {"detail": "This instance is already configured."},
                status=status.HTTP_409_CONFLICT,
            )
        except SetupNotAllowed:
            return Response(
                {"detail": "Creating an organization is not allowed."},
                status=status.HTTP_409_CONFLICT,
            )

        # login() needs an explicit backend since AUTHENTICATION_BACKENDS has
        # more than one entry and these users were created directly (not via
        # authenticate(), which normally stamps user.backend as a side effect).
        login(request, user, backend="apps.accounts.backends.EmailAuthBackend")
        return Response(status=status.HTTP_204_NO_CONTENT)


class MembershipViewSet(GenericViewSet):
    """List is open to any org member; mutations are administrator-only."""

    def get_permissions(self):
        if self.action == "list":
            return [IsOrganizationMember()]
        return [IsOrganizationAdministrator()]

    def list(self, request):
        memberships = get_organization_members(request.organization)
        page = self.paginate_queryset(memberships)
        serializer = MembershipSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def partial_update(self, request, pk=None):
        membership = get_object_or_404(get_organization_members(request.organization), pk=pk)
        serializer = MembershipRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            membership = change_member_role(
                membership=membership, new_role=serializer.validated_data["role"]
            )
        except LastAdministratorError:
            return Response(
                {"detail": "An organization must have at least one administrator."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(MembershipSerializer(membership).data)

    def destroy(self, request, pk=None):
        membership = get_object_or_404(get_organization_members(request.organization), pk=pk)
        try:
            remove_member(membership=membership)
        except LastAdministratorError:
            return Response(
                {"detail": "An organization must have at least one administrator."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationViewSet(GenericViewSet):
    permission_classes = [IsOrganizationAdministrator]
    # Constrains the router's detail route to Invitation's UUID pk so it
    # can never match a (much longer, non-hex) invitation token — otherwise
    # GET /api/invitations/<token>/ below would be shadowed by this route.
    lookup_value_regex = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

    def get_throttles(self):
        # Only `create` sends an email and creates a row an attacker could
        # otherwise use to spam arbitrary external addresses — list/destroy
        # have no comparable abuse surface, so only create is scoped.
        if self.action == "create":
            self.throttle_scope = "invitation-create"
        return super().get_throttles()

    def list(self, request):
        invitations = get_pending_invitations(request.organization)
        page = self.paginate_queryset(invitations)
        serializer = InvitationSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            invitation, raw_token = create_invitation(
                organization=request.organization,
                invited_by=request.user,
                email=serializer.validated_data["email"],
                role=serializer.validated_data["role"],
            )
        except MemberAlreadyExists:
            return Response(
                {"detail": "This email already belongs to a member of this organization."},
                status=status.HTTP_409_CONFLICT,
            )
        except InvitationAlreadyPending:
            return Response(
                {"detail": "An invitation is already pending for this email."},
                status=status.HTTP_409_CONFLICT,
            )

        invite_url = f"{settings.FRONTEND_BASE_URL}/invitations/{raw_token}"
        send_mail(
            subject=f"You've been invited to {request.organization.name} on Bug Fixer",
            message=(
                f"You've been invited to join {request.organization.name} on Bug "
                f"Fixer. Accept your invitation: {invite_url}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            fail_silently=True,
        )

        data = InvitationSerializer(invitation).data
        data["invite_url"] = invite_url
        return Response(data, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        invitation = get_object_or_404(get_pending_invitations(request.organization), pk=pk)
        revoke_invitation(invitation=invitation)
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationPublicDetailView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "invitation-lookup"

    def get(self, request, token):
        invitation = get_invitation_by_token(token)
        if invitation is None or not invitation.is_pending:
            return Response(
                {"detail": "This invitation is invalid or has expired."},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = {
            "organization_name": invitation.organization.name,
            "email": invitation.email,
            "role": invitation.role,
            "expires_at": invitation.expires_at,
        }
        return Response(InvitationPublicDetailSerializer(data).data)


@method_decorator(csrf_protect, name="dispatch")
class InvitationAcceptView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "invitation-accept"

    def post(self, request, token):
        serializer = InvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user, _membership = accept_invitation(
                raw_token=token,
                password=serializer.validated_data["password"],
                first_name=serializer.validated_data["first_name"],
                last_name=serializer.validated_data["last_name"],
            )
        except InvitationInvalid:
            return Response(
                {"detail": "This invitation is invalid or has expired."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # login() needs an explicit backend since AUTHENTICATION_BACKENDS has
        # more than one entry and these users were created directly (not via
        # authenticate(), which normally stamps user.backend as a side effect).
        login(request, user, backend="apps.accounts.backends.EmailAuthBackend")
        return Response(status=status.HTTP_204_NO_CONTENT)
