import uuid

import pytest

from apps.notifications.models import Notification, NotificationEventType
from apps.notifications.services import (
    is_email_enabled,
    list_resolved_preferences,
    mark_all_read,
    mark_read,
    notify,
    update_preference,
)


def _make_notification(organization, recipient, actor, bug, **extra):
    return Notification.objects.create(
        organization=organization,
        recipient=recipient,
        actor=actor,
        bug=bug,
        event_type=NotificationEventType.STATUS_CHANGED,
        dedup_key=f"status_changed:{uuid.uuid4()}",
        **extra,
    )


@pytest.mark.django_db
class TestMarkRead:
    def test_marks_an_unread_notification_read(self, organization, admin_user, developer_user, bug):
        notification = _make_notification(organization, developer_user, admin_user, bug)
        mark_read(notification=notification)
        notification.refresh_from_db()
        assert notification.read_at is not None

    def test_idempotent_on_an_already_read_notification(
        self, organization, admin_user, developer_user, bug
    ):
        notification = _make_notification(organization, developer_user, admin_user, bug)
        mark_read(notification=notification)
        first_read_at = notification.read_at
        mark_read(notification=notification)
        assert notification.read_at == first_read_at


@pytest.mark.django_db
class TestMarkAllRead:
    def test_marks_only_the_recipients_unread_notifications(
        self, organization, admin_user, developer_user, qa_user, bug
    ):
        mine_unread = _make_notification(organization, developer_user, admin_user, bug)
        mine_already_read = _make_notification(organization, developer_user, admin_user, bug)
        mark_read(notification=mine_already_read)
        someone_elses = _make_notification(organization, qa_user, admin_user, bug)

        updated = mark_all_read(organization=organization, recipient=developer_user)

        assert updated == 1
        mine_unread.refresh_from_db()
        someone_elses.refresh_from_db()
        assert mine_unread.read_at is not None
        assert someone_elses.read_at is None

    def test_returns_zero_when_nothing_is_unread(self, organization, developer_user):
        assert mark_all_read(organization=organization, recipient=developer_user) == 0


@pytest.mark.django_db
class TestPreferences:
    def test_missing_row_means_enabled(self, organization, developer_user):
        assert is_email_enabled(
            organization=organization,
            user=developer_user,
            event_type=NotificationEventType.MENTIONED,
        )

    def test_update_preference_disables_email(self, organization, developer_user):
        update_preference(
            organization=organization,
            user=developer_user,
            event_type=NotificationEventType.MENTIONED,
            email_enabled=False,
        )
        assert not is_email_enabled(
            organization=organization,
            user=developer_user,
            event_type=NotificationEventType.MENTIONED,
        )

    def test_update_preference_upserts(self, organization, developer_user):
        update_preference(
            organization=organization,
            user=developer_user,
            event_type=NotificationEventType.MENTIONED,
            email_enabled=False,
        )
        update_preference(
            organization=organization,
            user=developer_user,
            event_type=NotificationEventType.MENTIONED,
            email_enabled=True,
        )
        assert is_email_enabled(
            organization=organization,
            user=developer_user,
            event_type=NotificationEventType.MENTIONED,
        )

    def test_list_resolved_preferences_returns_every_community_event_type(
        self, organization, developer_user
    ):
        update_preference(
            organization=organization,
            user=developer_user,
            event_type=NotificationEventType.MENTIONED,
            email_enabled=False,
        )
        resolved = list_resolved_preferences(organization=organization, user=developer_user)
        assert {row["event_type"] for row in resolved} == set(NotificationEventType.values)
        by_type = {row["event_type"]: row["email_enabled"] for row in resolved}
        assert by_type[NotificationEventType.MENTIONED] is False
        assert by_type[NotificationEventType.COMMENT_ADDED] is True  # missing row -> enabled

    def test_list_resolved_preferences_issues_one_query(
        self, organization, developer_user, django_assert_num_queries
    ):
        update_preference(
            organization=organization,
            user=developer_user,
            event_type=NotificationEventType.MENTIONED,
            email_enabled=False,
        )
        with django_assert_num_queries(1):
            list_resolved_preferences(organization=organization, user=developer_user)


@pytest.mark.django_db(transaction=True)
class TestNotifyDispatch:
    def test_dispatches_after_commit(self, organization, admin_user, bug):
        from unittest.mock import patch

        with patch("apps.notifications.tasks.create_notifications_for_event.delay") as mock_delay:
            notify(
                event_type=NotificationEventType.STATUS_CHANGED,
                organization_id=organization.pk,
                bug_id=bug.pk,
                actor_id=admin_user.pk,
                activity_id=uuid.uuid4(),
            )
        mock_delay.assert_called_once()

    def test_broker_failure_does_not_raise(self, organization, admin_user, bug):
        from unittest.mock import patch

        with patch(
            "apps.notifications.tasks.create_notifications_for_event.delay",
            side_effect=ConnectionError("broker unreachable"),
        ):
            notify(
                event_type=NotificationEventType.STATUS_CHANGED,
                organization_id=organization.pk,
                bug_id=bug.pk,
                actor_id=admin_user.pk,
                activity_id=uuid.uuid4(),
            )  # must not raise

    def test_comment_events_require_comment_id(self, organization, admin_user, bug):
        with pytest.raises(ValueError):
            notify(
                event_type=NotificationEventType.MENTIONED,
                organization_id=organization.pk,
                bug_id=bug.pk,
                actor_id=admin_user.pk,
            )

    def test_non_comment_events_require_activity_id(self, organization, admin_user, bug):
        with pytest.raises(ValueError):
            notify(
                event_type=NotificationEventType.STATUS_CHANGED,
                organization_id=organization.pk,
                bug_id=bug.pk,
                actor_id=admin_user.pk,
            )
