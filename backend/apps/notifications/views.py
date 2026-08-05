from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from apps.notifications import selectors, services
from apps.notifications.models import Notification, NotificationEventType
from apps.notifications.serializers import (
    NotificationListQuerySerializer,
    NotificationPreferenceSerializer,
    NotificationSerializer,
    PreferenceUpdateSerializer,
)
from apps.organizations.permissions import IsOrganizationMember


def _detail_response(description: str) -> OpenApiResponse:
    return OpenApiResponse(
        response={"type": "object", "properties": {"detail": {"type": "string"}}},
        description=description,
    )


_FORBIDDEN_RESPONSE = _detail_response("The caller is authenticated but not permitted to do this.")
_NOT_FOUND_RESPONSE = _detail_response(
    "No notification with this id exists for the caller in their active organization."
)
_VALIDATION_ERROR_RESPONSE = OpenApiResponse(
    response={
        "type": "object",
        "additionalProperties": {"type": "array", "items": {"type": "string"}},
    },
    description="Structured per-field validation errors.",
)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            NotificationListQuerySerializer,
        ],
        responses={200: NotificationSerializer(many=True), 400: _VALIDATION_ERROR_RESPONSE},
    ),
)
class NotificationViewSet(GenericViewSet):
    """List/unread-count/read/mark-all-read for the caller's own
    notifications only. `recipient` is always request.user and
    `organization` is always request.organization — never accepted from the
    request — see apps.notifications.selectors.get_notifications_for_recipient,
    which is also what makes a cross-user or cross-organization notification
    id 404 rather than 403 (non-enumerating, matching every other app's
    identical convention)."""

    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsOrganizationMember]

    def get_object(self) -> Notification:
        return get_object_or_404(
            selectors.get_notification_for_recipient(self.request.organization, self.request.user),
            pk=self.kwargs["pk"],
        )

    def list(self, request):
        query = NotificationListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data

        read = None
        if "read" in data:
            read = data["read"] == "true"

        notifications = selectors.list_notifications(
            request.organization, request.user, read=read, event_type=data.get("event_type")
        )
        page = self.paginate_queryset(notifications)
        serializer = NotificationSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response={"type": "object", "properties": {"count": {"type": "integer"}}}
            )
        }
    )
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        count = selectors.unread_count(request.organization, request.user)
        return Response({"count": count})

    @extend_schema(
        request=None,
        responses={200: NotificationSerializer, 403: _FORBIDDEN_RESPONSE, 404: _NOT_FOUND_RESPONSE},
    )
    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        notification = services.mark_read(notification=self.get_object())
        return Response(NotificationSerializer(notification).data)

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(
                response={"type": "object", "properties": {"updated": {"type": "integer"}}}
            )
        },
    )
    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        updated = services.mark_all_read(organization=request.organization, recipient=request.user)
        return Response({"updated": updated})


class NotificationPreferenceListView(APIView):
    """All five Community event types, always — including ones with no
    NotificationPreference row yet, resolved against the "missing row means
    enabled" default. Never creates rows just because they were read; see
    apps.notifications.services.list_resolved_preferences."""

    permission_classes = [IsOrganizationMember]

    @extend_schema(responses={200: NotificationPreferenceSerializer(many=True)})
    def get(self, request):
        resolved = services.list_resolved_preferences(
            organization=request.organization, user=request.user
        )
        return Response(NotificationPreferenceSerializer(resolved, many=True).data)


class NotificationPreferenceDetailView(APIView):
    """Upserts the caller's own preference for one Community event type.
    event_type is validated against the enum (400, not 404 — it's a
    malformed request shape, not a missing resource). organization and user
    are always request.organization/request.user; nothing is ever accepted
    from the request body for either."""

    permission_classes = [IsOrganizationMember]

    @extend_schema(
        request=PreferenceUpdateSerializer,
        responses={
            200: NotificationPreferenceSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
        },
    )
    def patch(self, request, event_type=None):
        if event_type not in NotificationEventType.values:
            return Response(
                {"event_type": ["Unknown event type."]}, status=status.HTTP_400_BAD_REQUEST
            )

        serializer = PreferenceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        preference = services.update_preference(
            organization=request.organization,
            user=request.user,
            event_type=event_type,
            email_enabled=serializer.validated_data["email_enabled"],
        )
        return Response(
            NotificationPreferenceSerializer(
                {"event_type": preference.event_type, "email_enabled": preference.email_enabled}
            ).data
        )
