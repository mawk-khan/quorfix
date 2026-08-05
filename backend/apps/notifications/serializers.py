from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.bugs.serializers import BugRefSerializer
from apps.notifications.models import NotificationEventType


class NotificationSerializer(serializers.Serializer):
    """Deliberately a plain Serializer, not a ModelSerializer — the fields
    exposed here are an explicit allowlist. dedup_key, email_error,
    organization, recipient, and any internal task state are never listed,
    so there's no risk of a future model field silently becoming API-visible
    the way a ModelSerializer's implicit field discovery could allow."""

    id = serializers.UUIDField(read_only=True)
    event_type = serializers.ChoiceField(choices=NotificationEventType.choices, read_only=True)
    actor = UserSerializer(read_only=True)
    bug = BugRefSerializer(read_only=True)
    comment_id = serializers.UUIDField(read_only=True, allow_null=True)
    read_at = serializers.DateTimeField(read_only=True, allow_null=True)
    email_status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    target_url = serializers.SerializerMethodField()

    def get_target_url(self, obj) -> str:
        # Bug-level link only — no #comment-{id} anchor yet, since the
        # frontend has no comment-thread UI to scroll to (Chunk 1 was
        # backend-only). comment_id is still exposed above so a later
        # collaboration-frontend chunk can add deep linking without any
        # notification-model change.
        return f"/bugs/{obj.bug_id}"


class NotificationListQuerySerializer(serializers.Serializer):
    read = serializers.ChoiceField(choices=["true", "false"], required=False)
    event_type = serializers.ChoiceField(choices=NotificationEventType.choices, required=False)


class NotificationPreferenceSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=NotificationEventType.choices, read_only=True)
    email_enabled = serializers.BooleanField(read_only=True)


class PreferenceUpdateSerializer(serializers.Serializer):
    email_enabled = serializers.BooleanField()
