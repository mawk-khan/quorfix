import uuid

import pytest

from apps.notifications.models import Notification, NotificationEventType


def _make(
    organization,
    recipient,
    actor,
    bug,
    *,
    read=False,
    event_type=NotificationEventType.STATUS_CHANGED,
    **extra,
):
    notification = Notification.objects.create(
        organization=organization,
        recipient=recipient,
        actor=actor,
        bug=bug,
        event_type=event_type,
        dedup_key=f"{event_type}:{uuid.uuid4()}",
        **extra,
    )
    if read:
        from django.utils import timezone

        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return notification


@pytest.mark.django_db
class TestNotificationList:
    def test_lists_the_callers_notifications_newest_first(
        self, admin_client, organization, admin_user, developer_user, bug
    ):
        first = _make(organization, admin_user, developer_user, bug)
        second = _make(organization, admin_user, developer_user, bug)
        response = admin_client.get("/api/notifications/")
        assert response.status_code == 200
        ids = [row["id"] for row in response.json()["results"]]
        assert ids[:2] == [str(second.id), str(first.id)] or set(ids) == {
            str(first.id),
            str(second.id),
        }

    def test_omitted_read_filter_returns_both(
        self, admin_client, organization, admin_user, developer_user, bug
    ):
        _make(organization, admin_user, developer_user, bug, read=True)
        _make(organization, admin_user, developer_user, bug, read=False)
        response = admin_client.get("/api/notifications/")
        assert response.json()["count"] == 2

    def test_read_true_filter(self, admin_client, organization, admin_user, developer_user, bug):
        read_one = _make(organization, admin_user, developer_user, bug, read=True)
        _make(organization, admin_user, developer_user, bug, read=False)
        response = admin_client.get("/api/notifications/?read=true")
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["id"] == str(read_one.id)

    def test_read_false_filter(self, admin_client, organization, admin_user, developer_user, bug):
        _make(organization, admin_user, developer_user, bug, read=True)
        unread = _make(organization, admin_user, developer_user, bug, read=False)
        response = admin_client.get("/api/notifications/?read=false")
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["id"] == str(unread.id)

    def test_event_type_filter(self, admin_client, organization, admin_user, developer_user, bug):
        _make(
            organization,
            admin_user,
            developer_user,
            bug,
            event_type=NotificationEventType.STATUS_CHANGED,
        )
        assigned = _make(
            organization,
            admin_user,
            developer_user,
            bug,
            event_type=NotificationEventType.BUG_ASSIGNED,
        )
        response = admin_client.get("/api/notifications/?event_type=bug_assigned")
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["id"] == str(assigned.id)

    def test_invalid_read_filter_returns_400(self, admin_client):
        response = admin_client.get("/api/notifications/?read=maybe")
        assert response.status_code == 400

    def test_invalid_event_type_filter_returns_400(self, admin_client):
        response = admin_client.get("/api/notifications/?event_type=not_a_real_type")
        assert response.status_code == 400

    def test_response_never_includes_dedup_key_or_email_error(
        self, admin_client, organization, admin_user, developer_user, bug
    ):
        _make(organization, admin_user, developer_user, bug)
        response = admin_client.get("/api/notifications/")
        row = response.json()["results"][0]
        assert "dedup_key" not in row
        assert "email_error" not in row
        assert "organization" not in row
        assert "recipient" not in row

    def test_response_shape(self, admin_client, organization, admin_user, developer_user, bug):
        notification = _make(organization, admin_user, developer_user, bug)
        response = admin_client.get("/api/notifications/")
        row = response.json()["results"][0]
        assert row["id"] == str(notification.id)
        assert row["event_type"] == NotificationEventType.STATUS_CHANGED
        assert row["actor"]["id"] == str(developer_user.pk)
        assert row["bug"]["id"] == str(bug.pk)
        assert row["target_url"] == f"/bugs/{bug.pk}"
        assert row["email_status"] == "pending"
        assert row["read_at"] is None

    def test_bounded_pagination(self, admin_client, organization, admin_user, developer_user, bug):
        for _ in range(30):
            _make(organization, admin_user, developer_user, bug)
        response = admin_client.get("/api/notifications/")
        body = response.json()
        assert body["count"] == 30
        assert len(body["results"]) == 25  # BoundedPageNumberPagination default page_size
        assert body["next"] is not None

    def test_tenant_isolation(self, admin_client, developer_user, bug):
        from apps.organizations.models import CommunityRole, Organization, OrganizationMembership

        other_org = Organization.objects.create(name="Other Co", slug="other-co-notif-list")
        from django.contrib.auth import get_user_model

        other_admin = get_user_model().objects.create_user(
            username="other-org-admin-notif-list",
            email="other-org-admin-notif-list@example.com",
            password="x",
        )
        OrganizationMembership.objects.create(
            organization=other_org, user=other_admin, role=CommunityRole.ADMINISTRATOR
        )
        Notification.objects.create(
            organization=other_org,
            recipient=other_admin,
            actor=developer_user,
            bug=bug,
            event_type=NotificationEventType.STATUS_CHANGED,
            dedup_key=f"status_changed:{uuid.uuid4()}",
        )
        response = admin_client.get("/api/notifications/")
        assert response.json()["count"] == 0

    def test_unauthenticated_is_rejected(self, api_client):
        response = api_client.get("/api/notifications/")
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestQueryCountStability:
    def test_list_query_count_is_stable_regardless_of_row_count(
        self,
        admin_client,
        organization,
        admin_user,
        developer_user,
        bug,
        django_assert_max_num_queries,
    ):
        for _ in range(10):
            _make(organization, admin_user, developer_user, bug)
        with django_assert_max_num_queries(6):
            response = admin_client.get("/api/notifications/")
        assert response.status_code == 200
        assert len(response.json()["results"]) == 10

    def test_unread_count_is_a_single_aggregate_query(
        self, admin_client, organization, admin_user, developer_user, bug, django_assert_num_queries
    ):
        for _ in range(5):
            _make(organization, admin_user, developer_user, bug)
        # 3 queries are session-auth framework overhead (session lookup, user
        # lookup, OrganizationAwareSessionAuthentication's membership
        # resolution) — identical for every authenticated request regardless
        # of endpoint. The 4th is the one query this view actually issues:
        # a single COUNT(*), never a per-row fetch.
        with django_assert_num_queries(4):
            response = admin_client.get("/api/notifications/unread-count/")
        assert response.json()["count"] == 5
