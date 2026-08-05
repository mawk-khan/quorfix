import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.comments.models import Comment, CommentStatus, Mention


@pytest.mark.django_db
class TestCommentStatusConstraint:
    def test_valid_active_comment(self, bug, admin_user):
        comment = Comment.objects.create(
            organization=bug.organization, bug=bug, author=admin_user, body="Hello"
        )
        assert comment.status == CommentStatus.ACTIVE
        assert comment.deleted_at is None
        assert comment.redacted_at is None

    def test_valid_deleted_comment(self, bug, admin_user):
        comment = Comment.objects.create(
            organization=bug.organization,
            bug=bug,
            author=admin_user,
            body="",
            status=CommentStatus.DELETED,
            deleted_at=timezone.now(),
        )
        assert comment.deleted_at is not None
        assert comment.redacted_at is None

    def test_valid_redacted_comment(self, bug, admin_user):
        comment = Comment.objects.create(
            organization=bug.organization,
            bug=bug,
            author=admin_user,
            body="",
            status=CommentStatus.REDACTED,
            redacted_at=timezone.now(),
        )
        assert comment.redacted_at is not None
        assert comment.deleted_at is None

    def test_active_with_deleted_at_rejected(self, bug, admin_user):
        with pytest.raises(IntegrityError), transaction.atomic():
            Comment.objects.create(
                organization=bug.organization,
                bug=bug,
                author=admin_user,
                body="Hello",
                status=CommentStatus.ACTIVE,
                deleted_at=timezone.now(),
            )

    def test_deleted_without_deleted_at_rejected(self, bug, admin_user):
        with pytest.raises(IntegrityError), transaction.atomic():
            Comment.objects.create(
                organization=bug.organization,
                bug=bug,
                author=admin_user,
                body="",
                status=CommentStatus.DELETED,
            )

    def test_deleted_with_redacted_at_also_set_rejected(self, bug, admin_user):
        now = timezone.now()
        with pytest.raises(IntegrityError), transaction.atomic():
            Comment.objects.create(
                organization=bug.organization,
                bug=bug,
                author=admin_user,
                body="",
                status=CommentStatus.DELETED,
                deleted_at=now,
                redacted_at=now,
            )

    def test_redacted_without_redacted_at_rejected(self, bug, admin_user):
        with pytest.raises(IntegrityError), transaction.atomic():
            Comment.objects.create(
                organization=bug.organization,
                bug=bug,
                author=admin_user,
                body="",
                status=CommentStatus.REDACTED,
            )


@pytest.mark.django_db
class TestMentionConstraint:
    def test_unique_mention_per_comment_and_user(self, comment, developer_user):
        Mention.objects.create(
            organization=comment.organization, comment=comment, mentioned_user=developer_user
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            Mention.objects.create(
                organization=comment.organization, comment=comment, mentioned_user=developer_user
            )

    def test_same_user_mentioned_in_different_comments_allowed(
        self, bug, admin_user, admin_membership, developer_user, make_comment
    ):
        first = make_comment(bug, admin_user, membership=admin_membership, body="first")
        second = make_comment(bug, admin_user, membership=admin_membership, body="second")

        Mention.objects.create(
            organization=bug.organization, comment=first, mentioned_user=developer_user
        )
        Mention.objects.create(
            organization=bug.organization, comment=second, mentioned_user=developer_user
        )

        assert Mention.objects.filter(mentioned_user=developer_user).count() == 2
