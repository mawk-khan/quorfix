import uuid
from unittest.mock import patch

import pytest

from apps.comments.models import Mention
from apps.notifications.models import Notification, NotificationEmailStatus, NotificationEventType
from apps.notifications.tasks import create_notifications_for_event
from apps.organizations.models import CommunityRole, Organization, OrganizationMembership


def _run(**kwargs):
    """Runs the task synchronously against the real DB (mirrors
    apps.attachments.tests.test_removal's task.apply(...) pattern) without
    actually dispatching any email — email dispatch is asserted separately
    in test_email_tasks.py."""
    with patch("apps.notifications.tasks.send_notification_email.delay"):
        create_notifications_for_event.apply(kwargs=kwargs)


@pytest.mark.django_db
class TestSameEventDeduplication:
    def test_repeated_execution_creates_at_most_one_notification(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        activity_id = str(uuid.uuid4())
        bug.watchers.add(developer_user)
        kwargs = dict(
            event_type=NotificationEventType.STATUS_CHANGED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            activity_id=activity_id,
        )
        _run(**kwargs)
        _run(**kwargs)  # simulates a retried/redelivered task execution

        assert (
            Notification.objects.filter(
                organization=organization,
                recipient=developer_user,
                dedup_key=f"status_changed:{activity_id}",
            ).count()
            == 1
        )

    def test_get_or_create_relies_on_the_db_constraint_not_only_a_pre_check(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        """A row that already exists (e.g. inserted out-of-band) is still
        respected by a subsequent task execution — proves dedup is enforced
        by the unique constraint the get_or_create relies on, not merely by
        an in-memory "have I seen this already" check."""
        activity_id = str(uuid.uuid4())
        bug.watchers.add(developer_user)
        dedup_key = f"status_changed:{activity_id}"
        Notification.objects.create(
            organization=organization,
            recipient=developer_user,
            actor=admin_user,
            bug=bug,
            event_type=NotificationEventType.STATUS_CHANGED,
            dedup_key=dedup_key,
        )
        _run(
            event_type=NotificationEventType.STATUS_CHANGED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            activity_id=activity_id,
        )
        assert (
            Notification.objects.filter(organization=organization, dedup_key=dedup_key).count() == 1
        )


@pytest.mark.django_db
class TestCrossOrganizationDedupSafety:
    def test_same_dedup_key_in_different_organizations_is_allowed(
        self,
        organization,
        admin_user,
        developer_user,
        developer_membership,
        bug,
        make_project,
        make_bug,
    ):
        other_org = Organization.objects.create(name="Other Co", slug="other-co-notifications")
        other_admin = admin_user.__class__.objects.create_user(
            username="other-org-admin-notif",
            email="other-org-admin-notif@example.com",
            password="x",
        )
        OrganizationMembership.objects.create(
            organization=other_org, user=other_admin, role=CommunityRole.ADMINISTRATOR
        )
        other_dev = admin_user.__class__.objects.create_user(
            username="other-org-dev-notif", email="other-org-dev-notif@example.com", password="x"
        )
        OrganizationMembership.objects.create(
            organization=other_org, user=other_dev, role=CommunityRole.DEVELOPER
        )
        other_project = make_project(other_org, key="OTH")
        other_bug = make_bug(other_org, other_project, other_admin)
        other_bug.watchers.add(other_dev)

        activity_id = str(uuid.uuid4())  # deliberately the SAME activity_id across both orgs
        bug.watchers.add(developer_user)

        _run(
            event_type=NotificationEventType.STATUS_CHANGED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            activity_id=activity_id,
        )
        _run(
            event_type=NotificationEventType.STATUS_CHANGED,
            organization_id=str(other_org.pk),
            bug_id=str(other_bug.pk),
            actor_id=str(other_admin.pk),
            activity_id=activity_id,
        )

        dedup_key = f"status_changed:{activity_id}"
        assert (
            Notification.objects.filter(organization=organization, dedup_key=dedup_key).count() == 1
        )
        assert Notification.objects.filter(organization=other_org, dedup_key=dedup_key).count() == 1

    def test_bug_from_another_organization_is_rejected(self, organization, admin_user, bug):
        other_org = Organization.objects.create(name="Other Co 2", slug="other-co-notifications-2")
        _run(
            event_type=NotificationEventType.STATUS_CHANGED,
            organization_id=str(other_org.pk),
            bug_id=str(bug.pk),  # belongs to `organization`, not `other_org`
            actor_id=str(admin_user.pk),
            activity_id=str(uuid.uuid4()),
        )
        assert not Notification.objects.filter(bug=bug).exists()


@pytest.mark.django_db
class TestSameKeyDifferentRecipients:
    def test_same_dedup_key_for_different_recipients_is_allowed(
        self,
        organization,
        admin_user,
        developer_user,
        developer_membership,
        qa_user,
        qa_membership,
        bug,
    ):
        activity_id = str(uuid.uuid4())
        bug.watchers.add(developer_user, qa_user)
        _run(
            event_type=NotificationEventType.STATUS_CHANGED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            activity_id=activity_id,
        )
        dedup_key = f"status_changed:{activity_id}"
        assert (
            Notification.objects.filter(organization=organization, dedup_key=dedup_key).count() == 2
        )


@pytest.mark.django_db
class TestMentionPrecedence:
    def _mentioned_and_watching(
        self,
        organization,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        bug,
        make_comment,
    ):
        comment = make_comment(bug, admin_user, membership=admin_membership)
        Mention.objects.create(
            organization=organization, comment=comment, mentioned_user=developer_user
        )
        bug.watchers.add(developer_user)
        return comment

    def test_mentioned_recipient_does_not_also_receive_comment_added(
        self,
        organization,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        bug,
        make_comment,
    ):
        comment = self._mentioned_and_watching(
            organization,
            admin_user,
            admin_membership,
            developer_user,
            developer_membership,
            bug,
            make_comment,
        )
        _run(
            event_type=NotificationEventType.MENTIONED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            comment_id=str(comment.pk),
        )
        _run(
            event_type=NotificationEventType.COMMENT_ADDED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            comment_id=str(comment.pk),
        )

        notifications = Notification.objects.filter(
            organization=organization, recipient=developer_user, comment=comment
        )
        assert notifications.count() == 1
        assert notifications.get().event_type == NotificationEventType.MENTIONED

    def test_precedence_holds_regardless_of_task_execution_order(
        self,
        organization,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        bug,
        make_comment,
    ):
        comment = self._mentioned_and_watching(
            organization,
            admin_user,
            admin_membership,
            developer_user,
            developer_membership,
            bug,
            make_comment,
        )
        # comment_added dispatched and executed FIRST this time.
        _run(
            event_type=NotificationEventType.COMMENT_ADDED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            comment_id=str(comment.pk),
        )
        _run(
            event_type=NotificationEventType.MENTIONED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            comment_id=str(comment.pk),
        )

        notifications = Notification.objects.filter(
            organization=organization, recipient=developer_user, comment=comment
        )
        assert notifications.count() == 1
        assert notifications.get().event_type == NotificationEventType.MENTIONED

    def test_watcher_who_is_not_mentioned_receives_comment_added(
        self,
        organization,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        qa_user,
        qa_membership,
        bug,
        make_comment,
    ):
        comment = make_comment(bug, admin_user, membership=admin_membership)
        Mention.objects.create(
            organization=organization, comment=comment, mentioned_user=developer_user
        )
        bug.watchers.add(developer_user, qa_user)

        _run(
            event_type=NotificationEventType.COMMENT_ADDED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            comment_id=str(comment.pk),
        )

        assert not Notification.objects.filter(recipient=developer_user, comment=comment).exists()
        assert Notification.objects.filter(
            recipient=qa_user, comment=comment, event_type=NotificationEventType.COMMENT_ADDED
        ).exists()

    def test_actor_receives_neither_event(
        self,
        organization,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        bug,
        make_comment,
    ):
        # admin_user is both the comment author (actor) AND a watcher of their own bug.
        comment = make_comment(bug, admin_user, membership=admin_membership)
        Mention.objects.create(
            organization=organization, comment=comment, mentioned_user=admin_user
        )
        bug.watchers.add(admin_user, developer_user)

        _run(
            event_type=NotificationEventType.MENTIONED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            comment_id=str(comment.pk),
        )
        _run(
            event_type=NotificationEventType.COMMENT_ADDED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            comment_id=str(comment.pk),
        )

        assert not Notification.objects.filter(recipient=admin_user, comment=comment).exists()
        assert Notification.objects.filter(
            recipient=developer_user,
            comment=comment,
            event_type=NotificationEventType.COMMENT_ADDED,
        ).exists()


@pytest.mark.django_db
class TestEmailStatusAtCreation:
    def test_pending_when_email_enabled(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        activity_id = str(uuid.uuid4())
        bug.watchers.add(developer_user)
        _run(
            event_type=NotificationEventType.STATUS_CHANGED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            activity_id=activity_id,
        )
        notification = Notification.objects.get(organization=organization, recipient=developer_user)
        assert notification.email_status == NotificationEmailStatus.PENDING

    def test_disabled_when_preference_disables_email(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        from apps.notifications.services import update_preference

        update_preference(
            organization=organization,
            user=developer_user,
            event_type=NotificationEventType.STATUS_CHANGED,
            email_enabled=False,
        )
        activity_id = str(uuid.uuid4())
        bug.watchers.add(developer_user)
        _run(
            event_type=NotificationEventType.STATUS_CHANGED,
            organization_id=str(organization.pk),
            bug_id=str(bug.pk),
            actor_id=str(admin_user.pk),
            activity_id=activity_id,
        )
        notification = Notification.objects.get(organization=organization, recipient=developer_user)
        assert notification.email_status == NotificationEmailStatus.DISABLED
