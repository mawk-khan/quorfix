from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.bugs.models import BugStatus
from apps.bugs.services import assign_bug, transition_bug
from apps.comments.services import create_comment
from apps.notifications.models import Notification, NotificationEventType


def _dispatch_patch():
    # apps.notifications.services.notify dispatches via .apply_async (not
    # .delay) specifically so it can pass headers=correlation_headers() —
    # see apps.core.task_correlation. The business kwargs land under
    # call_args.kwargs["kwargs"] (apply_async's own "kwargs=" parameter),
    # not flat on call_args.kwargs the way a plain .delay(**kwargs) call
    # would put them.
    return patch("apps.notifications.tasks.create_notifications_for_event.apply_async")


@pytest.mark.django_db(transaction=True)
class TestAssignBugWiring:
    def test_real_assignment_change_dispatches_bug_assigned(
        self, bug, admin_user, admin_membership, developer_user, developer_membership
    ):
        with _dispatch_patch() as mock_delay:
            assign_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                assignee_id=developer_user.pk,
                expected_version=bug.version,
            )
        mock_delay.assert_called_once()
        assert (
            mock_delay.call_args.kwargs["kwargs"]["event_type"]
            == NotificationEventType.BUG_ASSIGNED
        )
        assert mock_delay.call_args.kwargs["kwargs"]["bug_id"] == str(bug.pk)
        assert mock_delay.call_args.kwargs["kwargs"]["assignee_id"] == str(developer_user.pk)
        assert mock_delay.call_args.kwargs["kwargs"]["activity_id"] is not None

    def test_noop_reassignment_dispatches_nothing(
        self, bug, admin_user, admin_membership, developer_user, developer_membership
    ):
        assign_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            assignee_id=developer_user.pk,
            expected_version=bug.version,
        )
        bug.refresh_from_db()
        with _dispatch_patch() as mock_delay:
            assign_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                assignee_id=developer_user.pk,
                expected_version=bug.version,
            )
        mock_delay.assert_not_called()

    def test_unassignment_dispatches_nothing(
        self, bug, admin_user, admin_membership, developer_user, developer_membership
    ):
        assign_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            assignee_id=developer_user.pk,
            expected_version=bug.version,
        )
        bug.refresh_from_db()
        with _dispatch_patch() as mock_delay:
            assign_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                assignee_id=None,
                expected_version=bug.version,
            )
        mock_delay.assert_not_called()


@pytest.mark.django_db(transaction=True)
class TestTransitionBugWiring:
    def test_ordinary_status_change_dispatches_status_changed_only(
        self, bug, admin_user, admin_membership
    ):
        with _dispatch_patch() as mock_delay:
            transition_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                new_status=BugStatus.TRIAGED,
                expected_version=bug.version,
            )
        mock_delay.assert_called_once()
        assert (
            mock_delay.call_args.kwargs["kwargs"]["event_type"]
            == NotificationEventType.STATUS_CHANGED
        )

    def test_reopen_dispatches_bug_reopened_not_status_changed(
        self, bug, admin_user, admin_membership, developer_user, developer_membership
    ):
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.TRIAGED,
            expected_version=bug.version,
        )
        bug.refresh_from_db()
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.ASSIGNED,
            expected_version=bug.version,
            assignee_id=developer_user.pk,
        )
        bug.refresh_from_db()
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.IN_PROGRESS,
            expected_version=bug.version,
        )
        bug.refresh_from_db()
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.RESOLVED,
            expected_version=bug.version,
        )
        bug.refresh_from_db()

        with _dispatch_patch() as mock_delay:
            transition_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                new_status=BugStatus.REOPENED,
                expected_version=bug.version,
            )

        mock_delay.assert_called_once()
        assert (
            mock_delay.call_args.kwargs["kwargs"]["event_type"]
            == NotificationEventType.BUG_REOPENED
        )

    def test_combined_status_and_assignment_change_dispatches_both_events(
        self, bug, admin_user, admin_membership, developer_user, developer_membership
    ):
        with _dispatch_patch() as mock_delay:
            transition_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                new_status=BugStatus.ASSIGNED,
                expected_version=bug.version,
                assignee_id=developer_user.pk,
            )
        event_types = {call.kwargs["kwargs"]["event_type"] for call in mock_delay.call_args_list}
        assert event_types == {
            NotificationEventType.BUG_ASSIGNED,
            NotificationEventType.STATUS_CHANGED,
        }

    def test_status_change_without_assignment_change_does_not_dispatch_bug_assigned(
        self, bug, admin_user, admin_membership
    ):
        with _dispatch_patch() as mock_delay:
            transition_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                new_status=BugStatus.TRIAGED,
                expected_version=bug.version,
            )
        event_types = {call.kwargs["kwargs"]["event_type"] for call in mock_delay.call_args_list}
        assert NotificationEventType.BUG_ASSIGNED not in event_types


@pytest.mark.django_db(transaction=True)
class TestCreateCommentWiring:
    def test_comment_without_mentions_dispatches_comment_added_only(
        self, bug, admin_user, admin_membership
    ):
        with _dispatch_patch() as mock_delay:
            create_comment(
                bug=bug, author=admin_user, membership=admin_membership, body="no mentions here"
            )
        event_types = [call.kwargs["kwargs"]["event_type"] for call in mock_delay.call_args_list]
        assert event_types == [NotificationEventType.COMMENT_ADDED]

    def test_comment_with_valid_mention_dispatches_both_events(
        self, bug, admin_user, admin_membership, developer_user, developer_membership
    ):
        body = f"hey @[Dev]({'mention:' + str(developer_user.pk)}) look at this"
        with _dispatch_patch() as mock_delay:
            create_comment(bug=bug, author=admin_user, membership=admin_membership, body=body)
        event_types = {call.kwargs["kwargs"]["event_type"] for call in mock_delay.call_args_list}
        assert event_types == {NotificationEventType.MENTIONED, NotificationEventType.COMMENT_ADDED}

    def test_comment_with_invalid_mention_token_dispatches_comment_added_only(
        self, bug, admin_user, admin_membership
    ):
        import uuid

        # syntactically valid mention token, but the id isn't a real member.
        body = f"hey @[Nobody](mention:{uuid.uuid4()}) look at this"
        with _dispatch_patch() as mock_delay:
            create_comment(bug=bug, author=admin_user, membership=admin_membership, body=body)
        event_types = [call.kwargs["kwargs"]["event_type"] for call in mock_delay.call_args_list]
        assert event_types == [NotificationEventType.COMMENT_ADDED]


@pytest.mark.django_db(transaction=True)
class TestEndToEndAssignmentNotification:
    """Regression coverage for a real bug caught while writing this suite:
    the initial wiring dispatched bug_assigned without forwarding
    assignee_id, so resolve_assignment_recipients had nothing to resolve and
    silently notified nobody. This runs the real Celery task body (only
    send_notification_email.apply_async is mocked) end-to-end instead of
    just asserting dispatch args, so a regression here would fail on a
    missing Notification row, not just a missing kwarg."""

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_assignee_actually_receives_a_notification(
        self, bug, admin_user, admin_membership, developer_user, developer_membership
    ):
        """Forces Celery eager mode explicitly rather than relying on the
        ambient DJANGO_SETTINGS_MODULE — create_notifications_for_event.
        apply_async is real (unmocked) here, and under
        config.settings.development (eager mode off) it would be sent to a
        real Redis broker with no in-process worker to consume it before the
        assertions below run. transaction.on_commit itself already fires
        correctly under this class's django_db(transaction=True) marker;
        that was never the problem. See test_transaction_dispatch.py for the
        mechanism proof and for broader transaction-boundary/broker-failure
        coverage."""
        with patch("apps.notifications.tasks.send_notification_email.apply_async"):
            assign_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                assignee_id=developer_user.pk,
                expected_version=bug.version,
            )
        notification = Notification.objects.get(
            organization=bug.organization,
            recipient=developer_user,
            event_type=NotificationEventType.BUG_ASSIGNED,
        )
        assert notification.bug_id == bug.pk
        assert notification.actor_id == admin_user.pk
        assert not Notification.objects.filter(
            organization=bug.organization, recipient=admin_user
        ).exists()
