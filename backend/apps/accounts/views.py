import logging

from django.conf import settings
from django.contrib.auth import authenticate, logout
from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import DemoLoginSerializer, LoginSerializer
from apps.accounts.services import resolve_demo_login_user, start_session

logger = logging.getLogger(__name__)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    """Authenticates by email + password and starts a session.

    Explicitly CSRF-protected: SessionAuthentication only enforces CSRF once
    it has resolved a user, which never happens for an anonymous login POST,
    so this view is decorated directly rather than relying on that.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            # Deliberately no submitted email or other request detail beyond
            # a fixed outcome string — logging the attempted address (even
            # only on failure) would let a log reader enumerate which
            # addresses are registered, exactly the side channel
            # EmailAuthBackend's own timing defense (apps.accounts.backends)
            # already exists to close off. request_id is already attached by
            # the logging filter, which is enough to correlate this with the
            # failed response without adding a new one here.
            logger.warning("Login failed")
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_session(request, user)
        logger.info("Login succeeded")
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class DemoLoginView(APIView):
    """Demo-only "Quick Access" login — authenticates as one of five fixed
    Quorfix Demo personas by role, never by password.

    Entirely inert unless settings.QUORFIX_DEMO_MODE is explicitly enabled
    (see .env.example) — returns 404 rather than 403 when disabled so this
    feature doesn't advertise its own existence on an ordinary Community
    installation. CSRF-protected the same way LoginView is, for the same
    reason: this is an anonymous POST that SessionAuthentication's CSRF
    enforcement never sees. Shares LoginView's "login" throttle scope
    rather than a separate one, so an attacker can't use this endpoint to
    get a second, independent brute-force budget.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    def post(self, request):
        if not settings.QUORFIX_DEMO_MODE:
            raise Http404()

        serializer = DemoLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        membership = resolve_demo_login_user(serializer.validated_data["role"])
        if membership is None:
            # Deliberately as generic as LoginView's own failure response —
            # see that view's comment for why no request detail is logged.
            logger.warning("Demo login failed")
            return Response(
                {"detail": "Demo login is currently unavailable."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_session(
            request,
            membership.user,
            backend="apps.accounts.backends.EmailAuthBackend",
            organization_id=membership.organization_id,
        )
        logger.info("Demo login succeeded")
        return Response(status=status.HTTP_204_NO_CONTENT)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.info("Logout")
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
