import uuid

import pytest
from rest_framework.test import APIClient

from apps.notifications.models import Notification, NotificationEventType


def _make(organization, recipient, actor, bug, **extra):
    return Notification.objects.create(
        organization=organization,
        recipient=recipient,
        actor=actor,
        bug=bug,
        event_type=NotificationEventType.STATUS_CHANGED,
        dedup_key=f"status_changed:{uuid.uuid4()}",
        **extra,
    )


@pytest.mark.django_db
class TestMarkOneRead:
    def test_marks_read(self, admin_client, organization, admin_user, developer_user, bug):
        notification = _make(organization, admin_user, developer_user, bug)
        response = admin_client.post(f"/api/notifications/{notification.id}/read/")
        assert response.status_code == 200
        assert response.json()["read_at"] is not None
        notification.refresh_from_db()
        assert notification.read_at is not None

    def test_idempotent_on_an_already_read_notification(
        self, admin_client, organization, admin_user, developer_user, bug
    ):
        notification = _make(organization, admin_user, developer_user, bug)
        first = admin_client.post(f"/api/notifications/{notification.id}/read/")
        second = admin_client.post(f"/api/notifications/{notification.id}/read/")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["read_at"] == second.json()["read_at"]

    def test_someone_elses_notification_404s(
        self, admin_client, organization, admin_user, developer_user, qa_user, qa_membership, bug
    ):
        notification = _make(
            organization, qa_user, developer_user, bug
        )  # recipient is qa_user, not admin_user
        response = admin_client.post(f"/api/notifications/{notification.id}/read/")
        assert response.status_code == 404

    def test_unknown_id_404s(self, admin_client):
        response = admin_client.post(f"/api/notifications/{uuid.uuid4()}/read/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestMarkAllRead:
    def test_returns_the_updated_count(
        self, admin_client, organization, admin_user, developer_user, bug
    ):
        _make(organization, admin_user, developer_user, bug)
        _make(organization, admin_user, developer_user, bug)
        response = admin_client.post("/api/notifications/mark-all-read/")
        assert response.status_code == 200
        assert response.json() == {"updated": 2}

    def test_idempotent_second_call_updates_zero(
        self, admin_client, organization, admin_user, developer_user, bug
    ):
        _make(organization, admin_user, developer_user, bug)
        admin_client.post("/api/notifications/mark-all-read/")
        second = admin_client.post("/api/notifications/mark-all-read/")
        assert second.json() == {"updated": 0}

    def test_does_not_affect_other_recipients(
        self, admin_client, organization, admin_user, developer_user, qa_user, qa_membership, bug
    ):
        someone_elses = _make(organization, qa_user, developer_user, bug)
        _make(organization, admin_user, developer_user, bug)
        admin_client.post("/api/notifications/mark-all-read/")
        someone_elses.refresh_from_db()
        assert someone_elses.read_at is None


@pytest.mark.django_db
class TestUnreadCount:
    def test_scoped_to_recipient_and_organization(
        self, admin_client, organization, admin_user, developer_user, qa_user, qa_membership, bug
    ):
        _make(organization, admin_user, developer_user, bug)
        _make(organization, admin_user, developer_user, bug)
        _make(organization, qa_user, developer_user, bug)  # a different recipient
        response = admin_client.get("/api/notifications/unread-count/")
        assert response.json() == {"count": 2}


@pytest.mark.django_db
class TestMembershipRemoval:
    def test_existing_notifications_preserved_after_membership_removal(
        self, organization, admin_user, admin_membership, developer_user, developer_membership, bug
    ):
        notification = _make(organization, developer_user, admin_user, bug)
        developer_membership.delete()
        assert Notification.objects.filter(pk=notification.pk).exists()

    def test_removed_member_cannot_access_the_notification_api(
        self, organization, admin_user, developer_user, developer_membership, bug
    ):
        client = APIClient()
        client.force_login(developer_user)
        assert client.get("/api/notifications/").status_code == 200

        developer_membership.delete()
        response = client.get("/api/notifications/")
        assert response.status_code == 403
