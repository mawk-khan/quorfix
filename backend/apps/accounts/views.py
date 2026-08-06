import logging

from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import LoginSerializer
from apps.core.context import bind_actor_context

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

        login(request, user)
        bind_actor_context(user_id=user.id)
        logger.info("Login succeeded")
        return Response(status=status.HTTP_204_NO_CONTENT)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.info("Logout")
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
