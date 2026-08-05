from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.activities.models import ActivityVerb, BugActivity
from apps.comments.models import Comment


def _backdate(comment, minutes, seconds_before_boundary=0):
    delta = timedelta(minutes=minutes) - timedelta(seconds=seconds_before_boundary)
    Comment.objects.filter(pk=comment.pk).update(created_at=timezone.now() - delta)
    comment.refresh_from_db()
    return comment


@pytest.mark.django_db
class TestEditWindow:
    def test_author_edit_inside_window_succeeds(self, admin_client, comment):
        response = admin_client.patch(
            f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/",
            {"body": "Updated body."},
            format="json",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["body"] == "Updated body."
        assert body["edited_at"] is not None

    def test_author_edit_just_inside_window_succeeds(self, admin_client, comment):
        # A few seconds' safety margin before the boundary — the exact instant
        # itself is covered deterministically at the unit level below, since
        # asserting on the literal boundary through two separate real
        # `timezone.now()` calls (backdate, then the view's own check) is
        # inherently racy at the API-test level.
        comment = _backdate(
            comment, settings.COMMENT_EDIT_WINDOW_MINUTES, seconds_before_boundary=5
        )
        response = admin_client.patch(
            f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/",
            {"body": "Just in time."},
            format="json",
        )
        assert response.status_code == 200

    def test_author_edit_outside_window_fails(self, admin_client, comment):
        comment = _backdate(comment, settings.COMMENT_EDIT_WINDOW_MINUTES + 1)
        response = admin_client.patch(
            f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/",
            {"body": "Too late."},
            format="json",
        )
        assert response.status_code == 409

    def test_non_author_edit_fails(self, developer_client, comment):
        response = developer_client.patch(
            f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/",
            {"body": "Rewriting someone else's words."},
            format="json",
        )
        assert response.status_code == 403

    def test_administrator_cannot_rewrite_another_users_comment(
        self, admin_client, bug, developer_user, developer_membership, make_comment
    ):
        # Administrators may redact/delete another user's comment, but never
        # silently rewrite its body — that power does not exist anywhere in
        # this app.
        other_comment = make_comment(bug, developer_user, membership=developer_membership)
        response = admin_client.patch(
            f"/api/bugs/{bug.pk}/comments/{other_comment.pk}/",
            {"body": "Rewritten by an admin."},
            format="json",
        )
        assert response.status_code == 403

    def test_edit_of_deleted_comment_fails(self, admin_client, comment):
        admin_client.delete(f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/")
        response = admin_client.patch(
            f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/",
            {"body": "Reviving a deleted comment."},
            format="json",
        )
        assert response.status_code == 409

    def test_edit_of_redacted_comment_fails(
        self,
        admin_client,
        developer_client,
        bug,
        developer_user,
        developer_membership,
        make_comment,
    ):
        target = make_comment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/comments/{target.pk}/redact/")
        response = developer_client.patch(
            f"/api/bugs/{bug.pk}/comments/{target.pk}/",
            {"body": "Reviving a redacted comment."},
            format="json",
        )
        assert response.status_code == 409

    def test_no_op_edit_creates_no_activity(self, admin_client, comment):
        before = BugActivity.objects.filter(
            bug=comment.bug, verb=ActivityVerb.COMMENT_EDITED
        ).count()
        response = admin_client.patch(
            f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/",
            {"body": comment.body},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["edited_at"] is None
        after = BugActivity.objects.filter(
            bug=comment.bug, verb=ActivityVerb.COMMENT_EDITED
        ).count()
        assert after == before

    def test_edit_records_activity(self, admin_client, comment):
        response = admin_client.patch(
            f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/",
            {"body": "Changed."},
            format="json",
        )
        assert response.status_code == 200
        assert (
            BugActivity.objects.filter(bug=comment.bug, verb=ActivityVerb.COMMENT_EDITED).count()
            == 1
        )

    def test_blank_body_rejected(self, admin_client, comment):
        response = admin_client.patch(
            f"/api/bugs/{comment.bug_id}/comments/{comment.pk}/", {"body": "   "}, format="json"
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestEditWindowBoundaryUnit:
    """Exercises apps.comments.policies.is_within_edit_window directly with an
    explicit `now`, so the exact-instant boundary is asserted deterministically
    instead of racing two independent wall-clock `timezone.now()` calls (the
    backdate and the check) the way an end-to-end API test would."""

    def test_exact_boundary_instant_is_within_window(self, comment):
        from apps.comments import policies

        boundary = comment.created_at + timedelta(minutes=settings.COMMENT_EDIT_WINDOW_MINUTES)
        assert policies.is_within_edit_window(comment, now=boundary) is True

    def test_one_microsecond_past_boundary_is_outside_window(self, comment):
        from apps.comments import policies

        just_after = (
            comment.created_at
            + timedelta(minutes=settings.COMMENT_EDIT_WINDOW_MINUTES)
            + timedelta(microseconds=1)
        )
        assert policies.is_within_edit_window(comment, now=just_after) is False
