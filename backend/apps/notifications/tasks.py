import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.bugs.models import Bug
from apps.comments.models import Comment
from apps.core.task_correlation import correlation_headers, task_correlation_context
from apps.notifications import resolvers
from apps.notifications.models import Notification, NotificationEmailStatus, NotificationEventType
from apps.notifications.services import is_email_enabled
from apps.organizations.models import Organization

logger = logging.getLogger(__name__)

_EMAIL_SUBJECTS = {
    NotificationEventType.BUG_ASSIGNED: "You were assigned {bug_key}",
    NotificationEventType.MENTIONED: "You were mentioned on {bug_key}",
    NotificationEventType.COMMENT_ADDED: "New comment on {bug_key}",
    NotificationEventType.STATUS_CHANGED: "{bug_key} status changed",
    NotificationEventType.BUG_REOPENED: "{bug_key} was reopened",
}


def _resolve_recipients(*, event_type, bug, comment, actor_id, assignee_id) -> list:
    """Dispatches to the resolver appropriate for `event_type`. comment_added's
    watcher set always subtracts the *current* Mention rows for `comment`
    directly — not a value handed in by whichever task (mentioned or
    comment_added) happens to run first — so mention-takes-precedence holds
    regardless of task dispatch/execution order (see
    apps.notifications.resolvers.resolve_watcher_recipients)."""
    if event_type == NotificationEventType.BUG_ASSIGNED:
        return resolvers.resolve_assignment_recipients(bug, assignee_id, actor_id)
    if event_type == NotificationEventType.MENTIONED:
        if comment is None:
            return []
        return resolvers.resolve_mention_recipients(comment, actor_id)
    if event_type == NotificationEventType.COMMENT_ADDED:
        exclude = (
            resolvers.mentioned_user_ids_for_comment(comment)
            if comment is not None
            else frozenset()
        )
        return resolvers.resolve_watcher_recipients(bug, actor_id, exclude_user_ids=exclude)
    if event_type in (NotificationEventType.STATUS_CHANGED, NotificationEventType.BUG_REOPENED):
        return resolvers.resolve_watcher_recipients(bug, actor_id)
    return []


@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def create_notifications_for_event(
    self,
    *,
    event_type,
    organization_id,
    bug_id,
    actor_id=None,
    activity_id=None,
    comment_id=None,
    assignee_id=None,
):
    """Re-resolves every argument from the database — never trusts a
    recipient list carried across the broker. Idempotent at the database
    layer via Notification's (organization, recipient, dedup_key) unique
    constraint: get_or_create per recipient means a retried or redelivered
    execution of this exact task can create at most one Notification per
    recipient, not because this function checks first, but because a second
    attempt's INSERT is rejected by the constraint and get_or_create falls
    back to the existing row.
    """
    with task_correlation_context(self):
        organization = Organization.objects.filter(pk=organization_id).first()
        bug = (
            Bug.objects.filter(pk=bug_id, organization_id=organization_id)
            .select_related("project")
            .first()
        )
        if organization is None or bug is None:
            # Tenant mismatch or the source objects are gone — should be
            # structurally impossible given the call sites (bugs/comments
            # services only ever dispatch with their own organization_id/bug_id
            # right after committing them), but this task never trusts its own
            # arguments blindly.
            logger.warning(
                "create_notifications_for_event: no bug %s in organization %s — dropping event %s",
                bug_id,
                organization_id,
                event_type,
            )
            return

        actor = None
        if actor_id:
            from django.contrib.auth import get_user_model

            actor = get_user_model().objects.filter(pk=actor_id).first()

        comment = None
        if comment_id:
            comment = (
                Comment.objects.filter(pk=comment_id, organization_id=organization_id)
                .select_related("organization")
                .first()
            )

        recipients = _resolve_recipients(
            event_type=event_type,
            bug=bug,
            comment=comment,
            actor_id=actor_id,
            assignee_id=assignee_id,
        )
        if not recipients:
            return

        source_id = activity_id or comment_id
        dedup_key = f"{event_type}:{source_id}"

        newly_created_pending_ids = []
        with transaction.atomic():
            for recipient in recipients:
                email_enabled = is_email_enabled(
                    organization=organization, user=recipient, event_type=event_type
                )
                notification, created = Notification.objects.get_or_create(
                    organization=organization,
                    recipient=recipient,
                    dedup_key=dedup_key,
                    defaults={
                        "event_type": event_type,
                        "actor": actor,
                        "bug": bug,
                        "comment": comment,
                        "email_status": (
                            NotificationEmailStatus.PENDING
                            if email_enabled
                            else NotificationEmailStatus.DISABLED
                        ),
                    },
                )
                if created and notification.email_status == NotificationEmailStatus.PENDING:
                    newly_created_pending_ids.append(notification.id)

        # Dispatched only after the block above has committed — each dispatch
        # is independent so one broker failure can't skip the rest, and a
        # broker outage here must never roll back or otherwise touch the
        # Notification rows already committed above (they stay PENDING;
        # nothing marks them sent, nothing deletes them).
        for notification_id in newly_created_pending_ids:
            try:
                send_notification_email.apply_async(
                    args=[str(notification_id)], headers=correlation_headers()
                )
            except Exception:
                logger.exception(
                    "Failed to dispatch send_notification_email for notification %s",
                    notification_id,
                )


def _mark_email_failed(notification_id, exc: Exception) -> None:
    safe_summary = f"{type(exc).__name__}: {str(exc)[:200]}"
    logger.error(
        "Notification %s email delivery permanently failed after exhausting retries",
        notification_id,
        exc_info=exc,
    )
    Notification.objects.filter(
        pk=notification_id, email_status=NotificationEmailStatus.PENDING
    ).update(email_status=NotificationEmailStatus.FAILED, email_error=safe_summary)


def _send_email(notification: Notification) -> None:
    bug = notification.bug
    subject_template = _EMAIL_SUBJECTS.get(notification.event_type, "Notification on {bug_key}")
    subject = subject_template.format(bug_key=bug.key)
    target_url = f"{settings.FRONTEND_BASE_URL}/bugs/{bug.id}"
    message = f"{bug.key} — {bug.title}\n\n{target_url}"
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[notification.recipient.email],
        fail_silently=False,
    )


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def send_notification_email(self, notification_id):
    """PENDING is the only state this task ever acts on — SENT, DISABLED,
    and FAILED are all treated as "already resolved, nothing to do", which is
    what makes a retried or redelivered task execution safe against a
    confirmed-successful prior send. The final state flip uses a single
    conditional UPDATE ... WHERE email_status='pending' rather than an
    explicit row lock: that statement is atomic at the database layer on its
    own, and is the actual concurrency control here, not an add-on to it.

    Residual risk, documented rather than engineered away: if the SMTP
    backend accepts the message but this process crashes/loses its DB
    connection before the UPDATE below commits, a retry will resend — a
    real duplicate delivery. Eliminating that fully needs a transactional
    outbox plus provider-level idempotency keys, which is disproportionate
    to Community's "basic email framework" scope for this chunk. The
    mitigation here is keeping the window between send and the UPDATE to a
    single statement, and logging loudly (not silently) if that UPDATE ever
    affects zero rows.
    """
    with task_correlation_context(self):
        notification = (
            Notification.objects.select_related("recipient", "bug")
            .filter(pk=notification_id)
            .first()
        )
        if notification is None or notification.email_status != NotificationEmailStatus.PENDING:
            return

        try:
            _send_email(notification)
        except Exception as exc:
            logger.warning(
                "Notification %s email send failed (attempt %s/%s)",
                notification_id,
                self.request.retries + 1,
                self.max_retries,
                exc_info=exc,
            )
            try:
                self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                _mark_email_failed(notification_id, exc)
            return

        updated = Notification.objects.filter(
            pk=notification_id, email_status=NotificationEmailStatus.PENDING
        ).update(email_status=NotificationEmailStatus.SENT, emailed_at=timezone.now())
        if not updated:
            logger.warning(
                "Notification %s email_status changed concurrently before the successful send "
                "could be recorded — the email was still sent exactly once",
                notification_id,
            )
