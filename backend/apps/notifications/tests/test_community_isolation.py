from unittest.mock import patch

import pytest
from django.apps import apps
from django.conf import settings

from apps.core.registries import (
    analytics_registry,
    automation_registry,
    capability_registry,
    integration_registry,
    workflow_registry,
)


def test_no_professional_apps_installed():
    """Notifications must work with every Professional module absent —
    today that's trivially true (backend/professional/ has no apps
    registered at all), but asserting it here means a future accidental
    `professional.*` addition to INSTALLED_APPS fails this test instead of
    silently coupling Community to Professional."""
    assert not any(app.startswith("professional.") for app in settings.INSTALLED_APPS)
    assert apps.is_installed("apps.notifications")


def test_registries_may_be_empty():
    """apps.notifications never reads any of these registries — nothing
    here (in-app notifications, the five Community events, per-user email
    preferences) is a Professional capability — but the registries
    themselves must tolerate being empty without raising, per
    apps.core.registries' own contract."""
    for registry in (
        capability_registry,
        workflow_registry,
        analytics_registry,
        integration_registry,
        automation_registry,
    ):
        assert registry.get("anything") is None


@pytest.mark.django_db(transaction=True)
def test_full_notification_lifecycle_works_with_professional_absent(
    admin_client,
    organization,
    admin_user,
    admin_membership,
    developer_user,
    developer_membership,
    bug,
):
    """Assign, comment (with a mention), read, and mark-all-read — the full
    Chunk 3 surface — end to end, exactly as a Community-only installation
    would run it, with no Professional module present anywhere in
    INSTALLED_APPS."""
    with patch("apps.notifications.tasks.send_notification_email.delay"):
        assign_response = admin_client.post(
            f"/api/bugs/{bug.pk}/assign/",
            {"assignee": str(developer_user.pk), "version": bug.version},
            format="json",
        )
        assert assign_response.status_code == 200

        mention_body = f"hey @[Dev](mention:{developer_user.pk}) take a look"
        comment_response = admin_client.post(
            f"/api/bugs/{bug.pk}/comments/", {"body": mention_body}, format="json"
        )
        assert comment_response.status_code == 201

    # admin_user is the actor for both events, not the recipient — the real
    # recipient here is developer_user (the assignee and the mentioned
    # user). Confirms the end-to-end pipeline actually produced rows, not
    # just that the API endpoints respond.
    from apps.notifications.models import Notification

    assert Notification.objects.filter(organization=organization, recipient=developer_user).exists()

    list_response = admin_client.get("/api/notifications/")
    assert list_response.status_code == 200
    unread_response = admin_client.get("/api/notifications/unread-count/")
    assert unread_response.status_code == 200

    mark_all = admin_client.post("/api/notifications/mark-all-read/")
    assert mark_all.status_code == 200

    preferences = admin_client.get("/api/notifications/preferences/")
    assert preferences.status_code == 200
