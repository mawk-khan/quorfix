from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.comments.models import Comment, CommentStatus


def _backdate(comment, minutes):
    Comment.objects.filter(pk=comment.pk).update(
        created_at=timezone.now() - timedelta(minutes=minutes)
    )
    comment.refresh_from_db()
    return comment


@pytest.mark.django_db
class TestDelete:
    def test_author_deletes_own_comment_inside_window(self, admin_client, comment):
        response = admin_client.delete(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "deleted"
        assert body["body"] == ""
        assert body["deleted_at"] is not None
        assert body["redacted_at"] is None

        comment.refresh_from_db()
        assert comment.status == CommentStatus.DELETED
        assert comment.body == ""
        # Author and creation time survive the deletion.
        assert comment.author_id is not None
        assert comment.created_at is not None

    def test_author_cannot_delete_outside_window(
        self, developer_client, bug, developer_user, developer_membership, make_comment
    ):
        # Must be a non-administrator author: an administrator is a moderator
        # and is exempt from the window regardless of authorship (see
        # test_administrator_deletes_any_active_comment_any_time below) — using
        # admin_client here would test the moderator bypass, not the window.
        own_comment = make_comment(bug, developer_user, membership=developer_membership)
        own_comment = _backdate(own_comment, settings.COMMENT_EDIT_WINDOW_MINUTES + 1)
        response = developer_client.delete(f"/api/bugs/{bug.pk}/comments/{own_comment.pk}/")
        assert response.status_code == 409
        own_comment.refresh_from_db()
        assert own_comment.status == CommentStatus.ACTIVE

    def test_administrator_deletes_any_active_comment_any_time(
        self, admin_client, bug, developer_user, developer_membership, make_comment
    ):
        target = make_comment(bug, developer_user, membership=developer_membership)
        target = _backdate(target, settings.COMMENT_EDIT_WINDOW_MINUTES + 100)
        response = admin_client.delete(f"/api/bugs/{bug.pk}/comments/{target.pk}/")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

    def test_non_author_non_admin_cannot_delete(
        self, qa_client, bug, developer_user, developer_membership, make_comment
    ):
        target = make_comment(bug, developer_user, membership=developer_membership)
        response = qa_client.delete(f"/api/bugs/{bug.pk}/comments/{target.pk}/")
        assert response.status_code == 403

    def test_repeated_delete_returns_409(self, admin_client, comment):
        admin_client.delete(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/")
        response = admin_client.delete(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/")
        assert response.status_code == 409


@pytest.mark.django_db
class TestRedact:
    def test_administrator_can_redact(self, admin_client, comment):
        response = admin_client.post(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/redact/")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "redacted"
        assert body["body"] == ""
        assert body["redacted_at"] is not None
        assert body["deleted_at"] is None

    def test_non_administrator_cannot_redact(self, developer_client, comment):
        response = developer_client.post(
            f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/redact/"
        )
        assert response.status_code == 403

    def test_author_cannot_redact_own_comment_without_admin_role(
        self, developer_client, bug, developer_user, developer_membership, make_comment
    ):
        own = make_comment(bug, developer_user, membership=developer_membership)
        response = developer_client.post(f"/api/bugs/{bug.pk}/comments/{own.pk}/redact/")
        assert response.status_code == 403

    def test_redaction_allowed_regardless_of_edit_window(self, admin_client, comment):
        comment = _backdate(comment, settings.COMMENT_EDIT_WINDOW_MINUTES + 1000)
        response = admin_client.post(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/redact/")
        assert response.status_code == 200

    def test_repeated_redact_returns_409(self, admin_client, comment):
        admin_client.post(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/redact/")
        response = admin_client.post(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/redact/")
        assert response.status_code == 409

    def test_redact_after_delete_returns_409(self, admin_client, comment):
        admin_client.delete(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/")
        response = admin_client.post(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/redact/")
        assert response.status_code == 409

    def test_delete_after_redact_returns_409(self, admin_client, comment):
        admin_client.post(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/redact/")
        response = admin_client.delete(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/")
        assert response.status_code == 409

    def test_redacted_comment_is_distinguishable_from_deleted(
        self, admin_client, bug, developer_user, developer_membership, make_comment
    ):
        deleted = make_comment(bug, developer_user, membership=developer_membership, body="one")
        redacted = make_comment(bug, developer_user, membership=developer_membership, body="two")
        admin_client.delete(f"/api/bugs/{bug.pk}/comments/{deleted.pk}/")
        admin_client.post(f"/api/bugs/{bug.pk}/comments/{redacted.pk}/redact/")

        response = admin_client.get(f"/api/bugs/{bug.pk}/comments/")
        results = {c["id"]: c for c in response.json()["results"]}
        assert results[str(deleted.pk)]["status"] == "deleted"
        assert results[str(redacted.pk)]["status"] == "redacted"


@pytest.mark.django_db
def test_deleted_comment_remains_serializable_in_thread(admin_client, comment):
    admin_client.delete(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/")
    response = admin_client.get(f"/api/bugs/{comment.bug_id}/comments/")
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["status"] == "deleted"
    assert results[0]["author"] is not None
    assert results[0]["created_at"] is not None
