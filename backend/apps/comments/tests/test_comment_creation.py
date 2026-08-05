import pytest

from apps.activities.models import ActivityVerb, BugActivity
from apps.comments.models import MAX_COMMENT_BODY_LENGTH


@pytest.mark.django_db
class TestCommentCreationValidation:
    def test_empty_body_rejected(self, admin_client, bug):
        response = admin_client.post(f"/api/bugs/{bug.pk}/comments/", {"body": ""}, format="json")
        assert response.status_code == 400
        assert "body" in response.json()

    def test_whitespace_only_body_rejected(self, admin_client, bug):
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/comments/", {"body": "   \n\t  "}, format="json"
        )
        assert response.status_code == 400
        assert "body" in response.json()

    def test_missing_body_rejected(self, admin_client, bug):
        response = admin_client.post(f"/api/bugs/{bug.pk}/comments/", {}, format="json")
        assert response.status_code == 400

    def test_body_over_max_length_rejected(self, admin_client, bug):
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/comments/",
            {"body": "x" * (MAX_COMMENT_BODY_LENGTH + 1)},
            format="json",
        )
        assert response.status_code == 400

    def test_body_at_max_length_accepted(self, admin_client, bug):
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/comments/",
            {"body": "x" * MAX_COMMENT_BODY_LENGTH},
            format="json",
        )
        assert response.status_code == 201


@pytest.mark.django_db
def test_successful_creation_records_exactly_one_comment_added_activity(admin_client, bug):
    response = admin_client.post(
        f"/api/bugs/{bug.pk}/comments/", {"body": "First comment."}, format="json"
    )
    assert response.status_code == 201
    assert BugActivity.objects.filter(bug=bug, verb=ActivityVerb.COMMENT_ADDED).count() == 1


@pytest.mark.django_db
def test_created_comment_response_shape(admin_client, bug):
    response = admin_client.post(
        f"/api/bugs/{bug.pk}/comments/", {"body": "Hello there."}, format="json"
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "active"
    assert body["body"] == "Hello there."
    assert body["edited_at"] is None
    assert body["deleted_at"] is None
    assert body["redacted_at"] is None
    assert body["mentions"] == []
    assert body["can_edit"] is True
    assert body["can_delete"] is True
    assert body["can_redact"] is True
    assert body["author"]["email"]
