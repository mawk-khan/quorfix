import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.comments.models import Comment


@pytest.mark.django_db
class TestPaginationAndOrdering:
    def test_list_is_bounded(self, admin_client, bug, admin_user, admin_membership, make_comment):
        for i in range(30):
            make_comment(bug, admin_user, membership=admin_membership, body=f"Comment {i}")

        response = admin_client.get(f"/api/bugs/{bug.pk}/comments/")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 30
        assert len(body["results"]) == 25
        assert body["next"] is not None

    def test_oldest_first_ordering(
        self, admin_client, bug, admin_user, admin_membership, make_comment
    ):
        first = make_comment(bug, admin_user, membership=admin_membership, body="first")
        second = make_comment(bug, admin_user, membership=admin_membership, body="second")
        third = make_comment(bug, admin_user, membership=admin_membership, body="third")

        response = admin_client.get(f"/api/bugs/{bug.pk}/comments/")
        ids = [c["id"] for c in response.json()["results"]]
        assert ids == [str(first.pk), str(second.pk), str(third.pk)]

    def test_stable_tie_breaker_for_identical_created_at(
        self, admin_client, bug, admin_user, admin_membership, make_comment
    ):
        first = make_comment(bug, admin_user, membership=admin_membership, body="first")
        second = make_comment(bug, admin_user, membership=admin_membership, body="second")

        # Force an identical created_at to prove ordering doesn't depend on
        # timestamp precision alone — the `id` tie-breaker must still produce
        # a deterministic order.
        tied_timestamp = first.created_at
        Comment.objects.filter(pk__in=[first.pk, second.pk]).update(created_at=tied_timestamp)

        expected = sorted([str(first.pk), str(second.pk)])
        response = admin_client.get(f"/api/bugs/{bug.pk}/comments/")
        ids = [c["id"] for c in response.json()["results"]]
        assert ids == expected


@pytest.mark.django_db
def test_list_query_count_does_not_grow_with_comment_count(
    admin_client,
    bug,
    admin_user,
    admin_membership,
    developer_user,
    developer_membership,
    make_comment,
):
    def _query_count():
        with CaptureQueriesContext(connection) as ctx:
            response = admin_client.get(f"/api/bugs/{bug.pk}/comments/")
        assert response.status_code == 200
        return len(ctx.captured_queries)

    make_comment(
        bug,
        admin_user,
        membership=admin_membership,
        body=f"Hey {f'@[Dev](mention:{developer_user.pk})'}",
    )
    small_count = _query_count()

    for i in range(10):
        make_comment(
            bug,
            admin_user,
            membership=admin_membership,
            body=f"Comment {i} @[Dev](mention:{developer_user.pk})",
        )
    large_count = _query_count()

    assert small_count == large_count


@pytest.mark.django_db
def test_list_query_count_bounded_with_multiple_mentions_per_comment(
    admin_client,
    bug,
    admin_user,
    admin_membership,
    developer_user,
    developer_membership,
    qa_user,
    qa_membership,
    reporter_user,
    reporter_membership,
    make_comment,
):
    """Focused regression for the serializer's mentions prefetch specifically
    (not just the author select_related covered above): every comment here
    carries multiple mentions of multiple different users, and authorship
    itself varies per comment — the query count must stay flat as both the
    comment count and the mention fan-out per comment grow."""

    def _query_count():
        with CaptureQueriesContext(connection) as ctx:
            response = admin_client.get(f"/api/bugs/{bug.pk}/comments/?page_size=100")
        assert response.status_code == 200
        return len(ctx.captured_queries), response.json()

    mention_targets = [developer_user, qa_user, reporter_user]

    def _body_mentioning_everyone(label):
        tokens = " ".join(f"@[{u.email}](mention:{u.pk})" for u in mention_targets)
        return f"{label} {tokens}"

    authors = [
        (admin_user, admin_membership),
        (developer_user, developer_membership),
        (qa_user, qa_membership),
    ]

    for i in range(3):
        author, membership = authors[i % len(authors)]
        make_comment(
            bug, author, membership=membership, body=_body_mentioning_everyone(f"small-{i}")
        )
    small_count, small_response = _query_count()

    for i in range(15):
        author, membership = authors[i % len(authors)]
        make_comment(
            bug, author, membership=membership, body=_body_mentioning_everyone(f"large-{i}")
        )
    large_count, large_response = _query_count()

    assert small_count == large_count

    # Authors and mentioned users actually made it into the response —
    # correctness, not just query count, since a broken prefetch could
    # otherwise return an empty `mentions` list just as cheaply.
    last_comment = large_response["results"][-1]
    assert last_comment["author"]["email"] in {u.email for u, _ in authors}
    mentioned_emails = {m["mentioned_user"]["email"] for m in last_comment["mentions"]}
    assert mentioned_emails == {u.email for u in mention_targets}
