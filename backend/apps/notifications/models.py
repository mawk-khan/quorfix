from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import OrganizationScopedModel


class NotificationEventType(models.TextChoices):
    BUG_ASSIGNED = "bug_assigned", "Bug assigned"
    MENTIONED = "mentioned", "Mentioned"
    COMMENT_ADDED = "comment_added", "Comment added"
    STATUS_CHANGED = "status_changed", "Status changed"
    BUG_REOPENED = "bug_reopened", "Bug reopened"


# Event types whose Notification row must reference the comment that
# triggered it — apps.notifications.services.notify() (the single write path
# for source-event args) enforces this before it ever reaches the DB, and the
# CheckConstraint below is the structural backstop for that invariant.
COMMENT_REQUIRED_EVENT_TYPES = frozenset(
    {NotificationEventType.MENTIONED, NotificationEventType.COMMENT_ADDED}
)


class NotificationEmailStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    DISABLED = "disabled", "Disabled"


class Notification(OrganizationScopedModel):
    """One in-app (always created) + optionally-emailed notification for a
    single recipient about a single source event (a BugActivity row for
    bug_assigned/status_changed/bug_reopened, a Comment row for
    mentioned/comment_added).

    Never created directly outside apps.notifications.tasks.
    create_notifications_for_event — see that module for why `dedup_key` is
    what actually makes retried/redelivered task execution safe, not just a
    pre-check.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    event_type = models.CharField(max_length=20, choices=NotificationEventType.choices)
    # Null means system-generated — mirrors apps.activities.models.BugActivity.actor.
    # Every Community event in this chunk has a real actor; nullable only to
    # keep this model consistent with that established convention for a
    # future system-generated event type.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    bug = models.ForeignKey("bugs.Bug", on_delete=models.CASCADE, related_name="notifications")
    comment = models.ForeignKey(
        "comments.Comment", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    # "{event_type}:{source_id}" — source_id is a BugActivity id for
    # bug_assigned/status_changed/bug_reopened, a Comment id for
    # mentioned/comment_added. Deliberately does NOT embed recipient_id:
    # recipient is already one of the three columns in the uniqueness
    # constraint below, so repeating it here would only lengthen the key
    # without adding safety.
    dedup_key = models.CharField(max_length=150)
    read_at = models.DateTimeField(null=True, blank=True)
    email_status = models.CharField(
        max_length=10,
        choices=NotificationEmailStatus.choices,
        default=NotificationEmailStatus.PENDING,
    )
    # A short, safe summary only (exception class name + truncated message) —
    # never a full traceback or a raw SMTP response. See
    # apps.notifications.tasks.send_notification_email.
    email_error = models.CharField(max_length=500, blank=True, default="")
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # Organization is included explicitly even though activity_id/
            # comment_id (the source_id half of dedup_key) are UUID4s and
            # already collision-resistant across organizations on their own —
            # this turns "safe because UUIDs don't collide" into "safe
            # because the schema forbids it", at no extra cost, matching
            # every other tenant-scoped unique constraint in this codebase
            # (unique_bug_key_per_org, unique_tag_name_per_org_ci, ...).
            models.UniqueConstraint(
                fields=["organization", "recipient", "dedup_key"], name="unique_notification_dedup"
            ),
            models.CheckConstraint(
                condition=(
                    Q(email_status=NotificationEmailStatus.PENDING, emailed_at__isnull=True)
                    | Q(
                        email_status=NotificationEmailStatus.SENT,
                        emailed_at__isnull=False,
                        email_error="",
                    )
                    | Q(
                        email_status=NotificationEmailStatus.DISABLED,
                        emailed_at__isnull=True,
                        email_error="",
                    )
                    | Q(email_status=NotificationEmailStatus.FAILED, emailed_at__isnull=True)
                ),
                name="notification_email_status_consistency",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        event_type__in=[
                            NotificationEventType.MENTIONED,
                            NotificationEventType.COMMENT_ADDED,
                        ],
                        comment__isnull=False,
                    )
                    | Q(
                        event_type__in=[
                            NotificationEventType.BUG_ASSIGNED,
                            NotificationEventType.STATUS_CHANGED,
                            NotificationEventType.BUG_REOPENED,
                        ]
                    )
                ),
                name="notification_comment_required_for_comment_events",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "recipient", "read_at"]),
            models.Index(fields=["organization", "recipient", "-created_at"]),
            models.Index(fields=["organization", "event_type", "created_at"]),
        ]
        # Newest-first with a stable id tie-breaker — matches
        # apps.activities.models.BugActivity's identical ordering convention.
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.event_type} -> {self.recipient_id} ({self.bug_id})"


class NotificationPreference(OrganizationScopedModel):
    """Per-user, per-organization, per-event-type email opt-out.

    A missing row means email-enabled — apps.notifications.services.
    is_email_enabled is the single source of truth for that default; this
    model only ever stores explicit overrides, never a pre-seeded row per
    event type.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=20, choices=NotificationEventType.choices)
    email_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user", "event_type"],
                name="unique_preference_per_org_user_event",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "user"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.organization_id} {self.event_type}={self.email_enabled}"
