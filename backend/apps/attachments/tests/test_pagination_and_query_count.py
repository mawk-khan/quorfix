import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext


@pytest.mark.django_db
class TestPaginationAndOrdering:
    def test_list_is_bounded(
        self, admin_client, bug, admin_user, admin_membership, make_uploaded_attachment
    ):
        for i in range(30):
            make_uploaded_attachment(
                bug, admin_user, membership=admin_membership, original_filename=f"file-{i}.txt"
            )

        response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 30
        assert len(body["results"]) == 25
        assert body["next"] is not None

    def test_oldest_first_ordering(
        self, admin_client, bug, admin_user, admin_membership, make_uploaded_attachment
    ):
        first = make_uploaded_attachment(
            bug, admin_user, membership=admin_membership, original_filename="a.txt"
        )
        second = make_uploaded_attachment(
            bug, admin_user, membership=admin_membership, original_filename="b.txt"
        )
        third = make_uploaded_attachment(
            bug, admin_user, membership=admin_membership, original_filename="c.txt"
        )

        response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/")
        ids = [a["id"] for a in response.json()["results"]]
        assert ids == [str(first.pk), str(second.pk), str(third.pk)]

    def test_stable_tie_breaker_for_identical_created_at(
        self, admin_client, bug, admin_user, admin_membership, make_uploaded_attachment
    ):
        from apps.attachments.models import Attachment

        first = make_uploaded_attachment(
            bug, admin_user, membership=admin_membership, original_filename="a.txt"
        )
        second = make_uploaded_attachment(
            bug, admin_user, membership=admin_membership, original_filename="b.txt"
        )

        tied_timestamp = first.created_at
        Attachment.objects.filter(pk__in=[first.pk, second.pk]).update(created_at=tied_timestamp)

        expected = sorted([str(first.pk), str(second.pk)])
        response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/")
        ids = [a["id"] for a in response.json()["results"]]
        assert ids == expected

    def test_pending_and_removed_never_appear_in_the_list(
        self,
        admin_client,
        bug,
        admin_user,
        admin_membership,
        make_attachment,
        make_uploaded_attachment,
    ):
        pending = make_attachment(bug, admin_user, membership=admin_membership)
        visible = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
        removed = make_uploaded_attachment(
            bug, admin_user, membership=admin_membership, original_filename="gone.txt"
        )
        admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{removed.pk}/")

        response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/")
        ids = {a["id"] for a in response.json()["results"]}
        assert ids == {str(visible.pk)}
        assert str(pending.pk) not in ids
        assert str(removed.pk) not in ids


@pytest.mark.django_db
def test_list_query_count_does_not_grow_with_attachment_count(
    admin_client, bug, admin_user, admin_membership, make_uploaded_attachment
):
    def _query_count():
        with CaptureQueriesContext(connection) as ctx:
            response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/?page_size=100")
        assert response.status_code == 200
        return len(ctx.captured_queries), response.json()

    make_uploaded_attachment(
        bug, admin_user, membership=admin_membership, original_filename="one.txt"
    )
    small_count, _ = _query_count()

    for i in range(15):
        make_uploaded_attachment(
            bug, admin_user, membership=admin_membership, original_filename=f"more-{i}.txt"
        )
    large_count, large_response = _query_count()

    assert small_count == large_count
    # uploaded_by serialization actually resolved, not just cheap to query.
    last = large_response["results"][-1]
    assert last["uploaded_by"]["email"] == admin_user.email
