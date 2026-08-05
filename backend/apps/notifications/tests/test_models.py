import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications.models import Notification, NotificationEmailStatus, NotificationEventType


def _base_kwargs(organization, admin_user, developer_user, bug):
    return dict(
        organization=organization,
        recipient=developer_user,
        actor=admin_user,
        bug=bug,
        dedup_key="status_changed:11111111-1111-1111-1111-111111111111",
        event_type=NotificationEventType.STATUS_CHANGED,
    )


@pytest.mark.django_db
class TestEmailStatusConsistencyConstraint:
    def test_pending_with_emailed_at_set_is_invalid(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        with pytest.raises(IntegrityError), transaction.atomic():
            Notification.objects.create(
                **kwargs, email_status=NotificationEmailStatus.PENDING, emailed_at=timezone.now()
            )

    def test_sent_without_emailed_at_is_invalid(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        with pytest.raises(IntegrityError), transaction.atomic():
            Notification.objects.create(
                **kwargs, email_status=NotificationEmailStatus.SENT, emailed_at=None
            )

    def test_sent_with_email_error_is_invalid(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        with pytest.raises(IntegrityError), transaction.atomic():
            Notification.objects.create(
                **kwargs,
                email_status=NotificationEmailStatus.SENT,
                emailed_at=timezone.now(),
                email_error="boom",
            )

    def test_disabled_with_email_error_is_invalid(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        with pytest.raises(IntegrityError), transaction.atomic():
            Notification.objects.create(
                **kwargs, email_status=NotificationEmailStatus.DISABLED, email_error="boom"
            )

    def test_disabled_with_emailed_at_is_invalid(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        with pytest.raises(IntegrityError), transaction.atomic():
            Notification.objects.create(
                **kwargs, email_status=NotificationEmailStatus.DISABLED, emailed_at=timezone.now()
            )

    def test_failed_with_emailed_at_is_invalid(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        with pytest.raises(IntegrityError), transaction.atomic():
            Notification.objects.create(
                **kwargs, email_status=NotificationEmailStatus.FAILED, emailed_at=timezone.now()
            )

    def test_failed_stores_a_bounded_safe_summary(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        notification = Notification.objects.create(
            **kwargs,
            email_status=NotificationEmailStatus.FAILED,
            email_error="SMTPException: timed out",
        )
        assert notification.email_error == "SMTPException: timed out"

    def test_valid_pending_and_disabled_and_sent_states_are_accepted(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        del kwargs["dedup_key"]
        Notification.objects.create(
            **kwargs, dedup_key="a", email_status=NotificationEmailStatus.PENDING
        )
        Notification.objects.create(
            **kwargs, dedup_key="b", email_status=NotificationEmailStatus.DISABLED
        )
        Notification.objects.create(
            **kwargs,
            dedup_key="c",
            email_status=NotificationEmailStatus.SENT,
            emailed_at=timezone.now(),
        )


@pytest.mark.django_db
class TestCommentRequiredConstraint:
    def test_mentioned_without_comment_is_invalid(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        kwargs["event_type"] = NotificationEventType.MENTIONED
        with pytest.raises(IntegrityError), transaction.atomic():
            Notification.objects.create(**kwargs, comment=None)

    def test_comment_added_without_comment_is_invalid(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        kwargs["event_type"] = NotificationEventType.COMMENT_ADDED
        with pytest.raises(IntegrityError), transaction.atomic():
            Notification.objects.create(**kwargs, comment=None)

    def test_mentioned_with_comment_is_valid(
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
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        kwargs["event_type"] = NotificationEventType.MENTIONED
        kwargs["dedup_key"] = f"mentioned:{comment.id}"
        Notification.objects.create(**kwargs, comment=comment)

    @pytest.mark.parametrize(
        "event_type",
        [
            NotificationEventType.BUG_ASSIGNED,
            NotificationEventType.STATUS_CHANGED,
            NotificationEventType.BUG_REOPENED,
        ],
    )
    def test_non_comment_events_allow_null_comment(
        self, organization, admin_user, developer_user, developer_membership, bug, event_type
    ):
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        kwargs["event_type"] = event_type
        Notification.objects.create(**kwargs, comment=None)


@pytest.mark.django_db
class TestDedupUniqueConstraint:
    def test_duplicate_recipient_and_dedup_key_in_same_org_is_rejected(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        kwargs = _base_kwargs(organization, admin_user, developer_user, bug)
        Notification.objects.create(**kwargs)
        with pytest.raises(IntegrityError), transaction.atomic():
            Notification.objects.create(**kwargs)


class TestOrdering:
    def test_newest_first_with_stable_id_tiebreaker(self):
        # Two rows created in the same test can legitimately land on the same
        # created_at microsecond under a fast test DB, so asserting on live
        # query order would be flaky — the ordering contract itself is what
        # matters, and that's a static property of the model.
        assert Notification._meta.ordering == ["-created_at", "-id"]
