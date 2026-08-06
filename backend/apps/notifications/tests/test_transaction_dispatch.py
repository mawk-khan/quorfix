"""Notification dispatch contract: transaction-boundary scheduling, eager
Celery integration, and broker-failure isolation.

Kept separate from test_event_wiring.py (which asserts *which* event type
each domain mutation dispatches, with create_notifications_for_event.delay
always mocked) and test_community_isolation.py (Professional-absence). This
file is specifically about *when* apps.notifications.services.notify's
transaction.on_commit callback fires relative to commit/rollback, and about
what happens when the broker itself is unreachable — see each test class's
docstring for the exact concern it covers.
"""

import logging
import uuid
from unittest.mock import patch

import pytest
from django.db import transaction
from django.test import override_settings

from apps.bugs.services import assign_bug
from apps.comments.models import Comment
from apps.comments.services import create_comment
from apps.notifications.models import Notification, NotificationEventType
from apps.notifications.services import notify
from apps.notifications.tasks import create_notifications_for_event


def test_celery_app_observes_override_settings_dynamically():
    """Guards the mechanism the eager-integration test below (and the two
    end-to-end tests fixed in test_event_wiring.py / test_community_isolation.py)
    rely on: config.celery.app reads CELERY_TASK_ALWAYS_EAGER from Django
    settings lazily (config_from_object("django.conf:settings", namespace=
    "CELERY") is consulted on each attribute access, not copied once at
    import time), so @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    reliably forces real task execution regardless of which
    DJANGO_SETTINGS_MODULE the process actually booted under. If a future
    Celery/Django upgrade changes that to eager-at-import caching, this test
    fails loudly here instead of the dependent tests failing mysteriously
    depending on ambient settings.

    Imports config.celery inside the test body, not at module load, so this
    assertion never depends on whether some earlier test in the suite
    already imported it first — an import-order dependency here would defeat
    the point of the assertion.
    """
    from config.celery import app as celery_app

    ambient_eager = celery_app.conf.task_always_eager
    with override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True):
        assert celery_app.conf.task_always_eager is True
        assert celery_app.conf.task_eager_propagates is True
    assert celery_app.conf.task_always_eager == ambient_eager


class TestCommitDispatchScheduling:
    """notify()'s only job is to register a transaction.on_commit callback
    that calls create_notifications_for_event.delay — these tests are about
    *when* that callback fires relative to commit, not about what the real
    Celery task does once it runs, so .delay is always mocked here."""

    @pytest.mark.django_db
    def test_dispatch_is_deferred_until_commit_and_carries_stable_ids(
        self, django_capture_on_commit_callbacks, organization, bug, admin_user, developer_user
    ):
        activity_id = uuid.uuid4()
        with patch("apps.notifications.tasks.create_notifications_for_event.delay") as mock_delay:
            with django_capture_on_commit_callbacks(execute=True) as callbacks:
                notify(
                    event_type=NotificationEventType.BUG_ASSIGNED,
                    organization_id=organization.id,
                    bug_id=bug.id,
                    actor_id=admin_user.id,
                    activity_id=activity_id,
                    assignee_id=developer_user.id,
                )
                # Still inside the captured block: the callback has been
                # registered but capture-mode defers it until the block
                # exits — it must not have run yet.
                mock_delay.assert_not_called()

            assert len(callbacks) == 1

        mock_delay.assert_called_once()
        kwargs = mock_delay.call_args.kwargs
        assert kwargs["event_type"] == NotificationEventType.BUG_ASSIGNED
        assert kwargs["organization_id"] == str(organization.id)
        assert kwargs["bug_id"] == str(bug.id)
        assert kwargs["actor_id"] == str(admin_user.id)
        assert kwargs["activity_id"] == str(activity_id)
        assert kwargs["assignee_id"] == str(developer_user.id)
        assert kwargs["comment_id"] is None


class TestRollbackSuppressesDispatch:
    """A rolled-back transaction must discard its on_commit callback along
    with its own writes — dispatching a notification for a mutation that
    never actually happened would be a real, user-visible bug."""

    @pytest.mark.django_db
    def test_exception_after_mutation_rolls_back_bug_change_and_never_dispatches(
        self, bug, admin_user, admin_membership, developer_user, developer_membership
    ):
        original_version = bug.version
        with patch("apps.notifications.tasks.create_notifications_for_event.delay") as mock_delay:
            with pytest.raises(RuntimeError):
                with transaction.atomic():
                    assign_bug(
                        bug=bug,
                        actor=admin_user,
                        membership=admin_membership,
                        assignee_id=developer_user.pk,
                        expected_version=bug.version,
                    )
                    raise RuntimeError("simulated failure after mutation, before outer commit")

        mock_delay.assert_not_called()
        bug.refresh_from_db()
        assert bug.assignee_id is None
        assert bug.version == original_version


class TestBrokerFailureIsolation:
    """create_notifications_for_event.delay talking to a dead/unreachable
    broker must never fail the bug/comment mutation that already committed
    by the time notify()'s on_commit callback runs — apps.notifications.
    services.notify's _dispatch swallows exactly this by design. Uses the
    plain db fixture + django_capture_on_commit_callbacks(execute=True)
    rather than transaction=True, so the callback fires deterministically
    without depending on a real commit."""

    @pytest.mark.django_db
    def test_assign_bug_commits_despite_broker_failure(
        self,
        django_capture_on_commit_callbacks,
        caplog,
        bug,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
    ):
        with patch(
            "apps.notifications.tasks.create_notifications_for_event.delay",
            side_effect=ConnectionError("broker unreachable"),
        ):
            with caplog.at_level(logging.ERROR, logger="apps.notifications.services"):
                with django_capture_on_commit_callbacks(execute=True):
                    result = assign_bug(
                        bug=bug,
                        actor=admin_user,
                        membership=admin_membership,
                        assignee_id=developer_user.pk,
                        expected_version=bug.version,
                    )

        assert result.assignee_id == developer_user.pk
        bug.refresh_from_db()
        assert bug.assignee_id == developer_user.pk
        assert any(
            record.levelno == logging.ERROR
            and "Failed to dispatch notification task" in record.getMessage()
            for record in caplog.records
        )

    @pytest.mark.django_db
    def test_create_comment_commits_despite_broker_failure(
        self,
        django_capture_on_commit_callbacks,
        caplog,
        bug,
        admin_user,
        admin_membership,
    ):
        with patch(
            "apps.notifications.tasks.create_notifications_for_event.delay",
            side_effect=ConnectionError("broker unreachable"),
        ):
            with caplog.at_level(logging.ERROR, logger="apps.notifications.services"):
                with django_capture_on_commit_callbacks(execute=True):
                    comment = create_comment(
                        bug=bug,
                        author=admin_user,
                        membership=admin_membership,
                        body="no mentions here",
                    )

        assert comment.pk is not None
        assert Comment.objects.filter(pk=comment.pk).exists()
        assert any(
            record.levelno == logging.ERROR
            and "Failed to dispatch notification task" in record.getMessage()
            for record in caplog.records
        )


class TestEagerTaskIntegration:
    """One real, non-mocked run of create_notifications_for_event, forced
    eager independent of the ambient DJANGO_SETTINGS_MODULE (see
    test_celery_app_observes_override_settings_dynamically above) — proves
    the actual recipient-resolution + dedup contract, not just that dispatch
    args look right. Only send_notification_email.delay is mocked, so no
    email is actually sent."""

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    @pytest.mark.django_db(transaction=True)
    def test_recipient_gets_exactly_one_notification_actor_gets_none_and_redelivery_dedupes(
        self, bug, admin_user, admin_membership, developer_user, developer_membership
    ):
        with patch("apps.notifications.tasks.send_notification_email.delay"):
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
        assert notification.actor_id == admin_user.pk
        assert not Notification.objects.filter(
            organization=bug.organization, recipient=admin_user
        ).exists()

        # Simulate a retried/redelivered Celery execution of the exact same
        # task message (identical stable source identifiers) — calling the
        # task function directly (not .delay) runs it synchronously in this
        # process, independent of eager mode, exactly like a broker
        # redelivering the same message a second time. The
        # (organization, recipient, dedup_key) unique constraint + the task's
        # get_or_create is what must make this a no-op — nothing added for
        # this test.
        activity_id = notification.dedup_key.split(":", 1)[1]
        with patch("apps.notifications.tasks.send_notification_email.delay") as email_delay_mock:
            create_notifications_for_event(
                event_type=NotificationEventType.BUG_ASSIGNED,
                organization_id=str(bug.organization_id),
                bug_id=str(bug.id),
                actor_id=str(admin_user.id),
                activity_id=activity_id,
                assignee_id=str(developer_user.id),
            )

        assert (
            Notification.objects.filter(
                organization=bug.organization,
                recipient=developer_user,
                event_type=NotificationEventType.BUG_ASSIGNED,
            ).count()
            == 1
        )
        email_delay_mock.assert_not_called()
