import pytest
from django.apps import apps
from django.conf import settings

from apps.attachments.models import ScanStatus
from apps.core.registries import (
    analytics_registry,
    automation_registry,
    capability_registry,
    integration_registry,
    workflow_registry,
)


def test_no_professional_apps_installed():
    assert not any(app.startswith("professional.") for app in settings.INSTALLED_APPS)
    assert apps.is_installed("apps.attachments")


def test_registries_may_be_empty():
    """apps.attachments never reads any registry except capability_registry's
    "malware_scanning" key, and only to check for absence — nothing here is a
    paywalled Professional feature."""
    for registry in (
        capability_registry,
        workflow_registry,
        analytics_registry,
        integration_registry,
        automation_registry,
    ):
        assert registry.get("anything") is None
    assert capability_registry.get("malware_scanning") is None


@pytest.mark.django_db
def test_attachment_lifecycle_works_with_no_scanner_registered(
    admin_client, bug, make_uploaded_attachment, admin_user, admin_membership
):
    attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
    attachment.refresh_from_db()
    assert attachment.scan_status == ScanStatus.NOT_SCANNED

    download = admin_client.get(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/download/")
    assert download.status_code == 200

    removal = admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
    assert removal.status_code == 200
