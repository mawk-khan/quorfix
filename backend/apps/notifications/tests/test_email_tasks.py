import logging
import uuid
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.notifications.models import Notification, NotificationEmailStatus, NotificationEventType
from apps.notifications.tasks import create_notifications_for_event, send_notification_email


def _make_notification(
    organization, recipient, actor, bug, *, email_status=NotificationEmailStatus.PENDING, **extra
):
    return Notification.objects.create(
        organization=organization,
        recipient=recipient,
        actor=actor,
        bug=bug,
        event_type=NotificationEventType.STATUS_CHANGED,
        dedup_key=f"status_changed:{uuid.uuid4()}",
        email_status=email_status,
        **extra,
    )


@pytest.mark.django_db
class TestDispatchFromCreation:
    def test_newly_created_pending_notification_dispatches_one_email_task(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        bug.watchers.add(developer_user)
        with patch("apps.notifications.tasks.send_notification_email.delay") as mock_delay:
            create_notifications_for_event.apply(
                kwargs=dict(
                    event_type=NotificationEventType.STATUS_CHANGED,
                    organization_id=str(organization.pk),
                    bug_id=str(bug.pk),
                    actor_id=str(admin_user.pk),
                    activity_id=str(uuid.uuid4()),
                )
            )
        mock_delay.assert_called_once()
        notification = Notification.objects.get(organization=organization, recipient=developer_user)
        assert str(notification.id) == mock_delay.call_args.args[0]

    def test_repeated_execution_does_not_dispatch_another_email_for_an_existing_notification(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        bug.watchers.add(developer_user)
        activity_id = str(uuid.uuid4())
        kwargs = dict(
            event_type=NotificationEventType.STATUS_CHANGED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            activity_id=activity_id,
        )
        with patch("apps.notifications.tasks.send_notification_email.delay") as mock_delay:
            create_notifications_for_event.apply(kwargs=kwargs)
            create_notifications_for_event.apply(kwargs=kwargs)
        mock_delay.assert_called_once()

    def test_disabled_preference_creates_notification_but_no_email_task(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        from apps.notifications.services import update_preference

        update_preference(
            organization=organization,
            user=developer_user,
            event_type=NotificationEventType.STATUS_CHANGED,
            email_enabled=False,
        )
        bug.watchers.add(developer_user)
        with patch("apps.notifications.tasks.send_notification_email.delay") as mock_delay:
            create_notifications_for_event.apply(
                kwargs=dict(
                    event_type=NotificationEventType.STATUS_CHANGED,
                    organization_id=str(organization.pk),
                    bug_id=str(bug.pk),
                    actor_id=str(admin_user.pk),
                    activity_id=str(uuid.uuid4()),
                )
            )
        mock_delay.assert_not_called()
        notification = Notification.objects.get(organization=organization, recipient=developer_user)
        assert notification.email_status == NotificationEmailStatus.DISABLED

    def test_broker_failure_dispatching_email_leaves_notification_intact(
        self, organization, admin_user, developer_user, developer_membership, bug, caplog
    ):
        bug.watchers.add(developer_user)
        with (
            patch(
                "apps.notifications.tasks.send_notification_email.delay",
                side_effect=ConnectionError("broker unreachable"),
            ),
            caplog.at_level(logging.ERROR),
        ):
            create_notifications_for_event.apply(
                kwargs=dict(
                    event_type=NotificationEventType.STATUS_CHANGED,
                    organization_id=str(organization.pk),
                    bug_id=str(bug.pk),
                    actor_id=str(admin_user.pk),
                    activity_id=str(uuid.uuid4()),
                )
            )
        notification = Notification.objects.get(organization=organization, recipient=developer_user)
        assert notification.email_status == NotificationEmailStatus.PENDING
        assert notification.emailed_at is None
        assert any("Failed to dispatch" in record.message for record in caplog.records)


@pytest.mark.django_db
class TestSendNotificationEmailNoOps:
    def test_sent_notification_is_a_noop(self, organization, admin_user, developer_user, bug):
        notification = _make_notification(
            organization,
            developer_user,
            admin_user,
            bug,
            email_status=NotificationEmailStatus.SENT,
            emailed_at=timezone.now(),
        )
        with patch("apps.notifications.tasks.send_mail") as mock_send:
            send_notification_email.apply(args=[str(notification.id)])
        mock_send.assert_not_called()

    def test_disabled_notification_is_a_noop(self, organization, admin_user, developer_user, bug):
        notification = _make_notification(
            organization,
            developer_user,
            admin_user,
            bug,
            email_status=NotificationEmailStatus.DISABLED,
        )
        with patch("apps.notifications.tasks.send_mail") as mock_send:
            send_notification_email.apply(args=[str(notification.id)])
        mock_send.assert_not_called()

    def test_failed_notification_is_a_noop(self, organization, admin_user, developer_user, bug):
        notification = _make_notification(
            organization,
            developer_user,
            admin_user,
            bug,
            email_status=NotificationEmailStatus.FAILED,
            email_error="SMTPException: boom",
        )
        with patch("apps.notifications.tasks.send_mail") as mock_send:
            send_notification_email.apply(args=[str(notification.id)])
        mock_send.assert_not_called()
        notification.refresh_from_db()
        assert notification.email_error == "SMTPException: boom"  # untouched

    def test_missing_notification_is_a_noop(self):
        with patch("apps.notifications.tasks.send_mail") as mock_send:
            send_notification_email.apply(args=[str(uuid.uuid4())])
        mock_send.assert_not_called()


@pytest.mark.django_db
class TestSendNotificationEmailSuccess:
    def test_pending_notification_is_sent_and_marked_sent(
        self, organization, admin_user, developer_user, bug
    ):
        notification = _make_notification(organization, developer_user, admin_user, bug)
        send_notification_email.apply(args=[str(notification.id)])
        notification.refresh_from_db()
        assert notification.email_status == NotificationEmailStatus.SENT
        assert notification.emailed_at is not None

        from django.core import mail

        assert len(mail.outbox) == 1
        assert notification.recipient.email in mail.outbox[0].to


@pytest.mark.django_db
class TestSendNotificationEmailRetryAndFailure:
    def test_transient_failure_retries(self, organization, admin_user, developer_user, bug):
        notification = _make_notification(organization, developer_user, admin_user, bug)
        with (
            patch("apps.notifications.tasks.send_mail", side_effect=ConnectionError("smtp down")),
            patch.object(send_notification_email, "retry") as mock_retry,
        ):
            send_notification_email.apply(args=[str(notification.id)])
        mock_retry.assert_called_once()
        notification.refresh_from_db()
        assert notification.email_status == NotificationEmailStatus.PENDING  # not yet exhausted

    def test_exhausted_retries_set_failed_state_with_a_safe_bounded_summary(
        self, organization, admin_user, developer_user, bug, caplog
    ):
        notification = _make_notification(organization, developer_user, admin_user, bug)

        def _raise_exhausted(*args, **kwargs):
            raise send_notification_email.MaxRetriesExceededError()

        long_message = "x" * 1000  # must be truncated, not stored raw
        with (
            patch("apps.notifications.tasks.send_mail", side_effect=Exception(long_message)),
            patch.object(send_notification_email, "retry", side_effect=_raise_exhausted),
            caplog.at_level(logging.ERROR),
        ):
            send_notification_email.apply(args=[str(notification.id)])

        notification.refresh_from_db()
        assert notification.email_status == NotificationEmailStatus.FAILED
        assert notification.emailed_at is None
        assert len(notification.email_error) <= 500
        assert notification.email_error.startswith("Exception:")
        assert any("permanently failed" in record.message for record in caplog.records)
        # The full exception detail goes to the server log, not the stored field.
        assert any(
            long_message in (record.exc_text or "") for record in caplog.records if record.exc_info
        )

    def test_final_update_is_a_noop_if_status_changed_concurrently(
        self, organization, admin_user, developer_user, bug, caplog
    ):
        """Simulates a concurrent worker having already recorded this exact
        send while our own send_mail call was in flight — the conditional
        UPDATE...WHERE email_status='pending' must affect zero rows rather
        than raise or overwrite the concurrent result, and the situation
        must be logged, not silently swallowed."""
        notification = _make_notification(organization, developer_user, admin_user, bug)

        def _simulate_concurrent_sent(*args, **kwargs):
            Notification.objects.filter(pk=notification.pk).update(
                email_status=NotificationEmailStatus.SENT, emailed_at=timezone.now()
            )

        with (
            patch("apps.notifications.tasks.send_mail", side_effect=_simulate_concurrent_sent),
            caplog.at_level(logging.WARNING),
        ):
            send_notification_email.apply(args=[str(notification.id)])

        notification.refresh_from_db()
        assert notification.email_status == NotificationEmailStatus.SENT
        assert any("changed concurrently" in record.message for record in caplog.records)
