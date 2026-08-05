import logging

from django.db import transaction
from django.utils import timezone

from apps.notifications.models import (
    COMMENT_REQUIRED_EVENT_TYPES,
    Notification,
    NotificationEventType,
    NotificationPreference,
)

logger = logging.getLogger(__name__)


# -- event dispatch (called from apps.bugs.services / apps.comments.services) --


def notify(
    *,
    event_type: str,
    organization_id,
    bug_id,
    actor_id=None,
    activity_id=None,
    comment_id=None,
    assignee_id=None,
) -> None:
    """The single dispatch path from bugs/comments services into the
    notifications Celery pipeline — called via a function-local import,
    mirroring how those modules already import apps.activities.services.

    Wraps the actual .delay() in transaction.on_commit + a swallowed
    try/except, exactly like apps.attachments.services.remove_attachment's
    _dispatch_cleanup: a broker outage here must never surface as a failure
    of the bug/comment mutation that already committed by the time this
    callback runs.

    Validates the comment_id/activity_id shape immediately (synchronously,
    at the call site) rather than only via the Notification model's
    CheckConstraint deep inside a background task — a programming error at
    a call site should fail loudly and immediately in tests, not silently
    inside a Celery task minutes later.
    """
    if event_type in COMMENT_REQUIRED_EVENT_TYPES:
        if comment_id is None:
            raise ValueError(f"{event_type} notifications require a comment_id")
    elif activity_id is None:
        raise ValueError(f"{event_type} notifications require an activity_id")

    def _dispatch():
        from apps.notifications.tasks import create_notifications_for_event

        try:
            create_notifications_for_event.delay(
                event_type=event_type,
                organization_id=str(organization_id),
                bug_id=str(bug_id),
                actor_id=str(actor_id) if actor_id else None,
                activity_id=str(activity_id) if activity_id else None,
                comment_id=str(comment_id) if comment_id else None,
                assignee_id=str(assignee_id) if assignee_id else None,
            )
        except Exception:
            logger.exception(
                "Failed to dispatch notification task for event %s on bug %s", event_type, bug_id
            )

    transaction.on_commit(_dispatch)


# -- read state -----------------------------------------------------------


def mark_read(*, notification: Notification) -> Notification:
    """Idempotent — marking an already-read notification read again is a
    no-op, not an error."""
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return notification


def mark_all_read(*, organization, recipient) -> int:
    return Notification.objects.filter(
        organization=organization, recipient=recipient, read_at__isnull=True
    ).update(read_at=timezone.now())


# -- preferences ------------------------------------------------------------


def is_email_enabled(*, organization, user, event_type: str) -> bool:
    """Missing row means enabled — this is the one place that default is
    encoded; every other read path (the preferences list endpoint, the
    Celery task deciding a new Notification's initial email_status) goes
    through here or through list_resolved_preferences below, never
    re-derives the default independently."""
    preference = NotificationPreference.objects.filter(
        organization=organization, user=user, event_type=event_type
    ).first()
    if preference is None:
        return True
    return preference.email_enabled


def list_resolved_preferences(*, organization, user) -> list[dict]:
    """One query for every existing override, then filled out against the
    full Community event-type enum in Python — never one query per event
    type, and never creates a row just because it was read."""
    existing = {
        preference.event_type: preference.email_enabled
        for preference in NotificationPreference.objects.filter(
            organization=organization, user=user
        )
    }
    return [
        {"event_type": event_type, "email_enabled": existing.get(event_type, True)}
        for event_type in NotificationEventType.values
    ]


def update_preference(
    *, organization, user, event_type: str, email_enabled: bool
) -> NotificationPreference:
    preference, _created = NotificationPreference.objects.update_or_create(
        organization=organization,
        user=user,
        event_type=event_type,
        defaults={"email_enabled": email_enabled},
    )
    return preference
