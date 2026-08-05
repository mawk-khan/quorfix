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
    """Comments must work with every Professional module absent — today that's
    trivially true (backend/professional/ has no apps registered at all), but
    asserting it here means a future accidental `professional.*` addition to
    INSTALLED_APPS fails this test instead of silently coupling Community to
    Professional."""
    assert not any(app.startswith("professional.") for app in settings.INSTALLED_APPS)
    assert apps.is_installed("apps.comments")


def test_registries_may_be_empty():
    """apps.comments never reads any of these registries — nothing here is a
    Professional capability — but the registries themselves must tolerate
    being empty without raising, per apps.core.registries' own contract."""
    for registry in (
        capability_registry,
        workflow_registry,
        analytics_registry,
        integration_registry,
        automation_registry,
    ):
        assert registry.get("anything") is None


@pytest.mark.django_db
def test_comment_lifecycle_works_with_professional_absent(admin_client, bug):
    create = admin_client.post(
        f"/api/bugs/{bug.pk}/comments/", {"body": "Works standalone."}, format="json"
    )
    assert create.status_code == 201
    comment_id = create.json()["id"]

    edit = admin_client.patch(
        f"/api/bugs/{bug.pk}/comments/{comment_id}/", {"body": "Still works."}, format="json"
    )
    assert edit.status_code == 200

    delete = admin_client.delete(f"/api/bugs/{bug.pk}/comments/{comment_id}/")
    assert delete.status_code == 200
