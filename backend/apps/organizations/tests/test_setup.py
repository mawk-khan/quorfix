import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
from apps.organizations.services import (
    SetupAlreadyCompleted,
    is_instance_configured,
    setup_instance,
)


@pytest.mark.django_db
class TestSetupInstanceService:
    def test_creates_admin_org_and_membership(self, password):
        user, org, membership = setup_instance(
            organization_name="Acme",
            email="admin@example.com",
            password=password,
        )
        assert Organization.objects.filter(pk=org.pk).exists()
        assert membership.role == CommunityRole.ADMINISTRATOR
        assert membership.user_id == user.pk
        assert is_instance_configured() is True

    def test_second_call_raises_already_completed(self, password):
        setup_instance(organization_name="Acme", email="admin@example.com", password=password)
        with pytest.raises(SetupAlreadyCompleted):
            setup_instance(
                organization_name="Other", email="other@example.com", password=password
            )
        # Only the first organization/membership exist.
        assert Organization.objects.count() == 1
        assert OrganizationMembership.objects.count() == 1


@pytest.mark.django_db
class TestSetupView:
    def test_status_reports_not_configured(self, api_client):
        response = api_client.get("/api/setup/")
        assert response.status_code == 200
        assert response.json() == {"is_configured": False}

    def test_status_reports_configured_after_setup(self, api_client, password):
        setup_instance(organization_name="Acme", email="admin@example.com", password=password)
        response = api_client.get("/api/setup/")
        assert response.json() == {"is_configured": True}

    def test_setup_creates_instance_and_logs_in(self, api_client, password):
        response = api_client.post(
            "/api/setup/",
            {
                "organization_name": "Acme",
                "email": "admin@example.com",
                "password": password,
            },
        )
        assert response.status_code == 204
        assert "_auth_user_id" in api_client.session
        assert OrganizationMembership.objects.get().role == CommunityRole.ADMINISTRATOR

    def test_setup_rejected_once_already_configured(self, api_client, password):
        setup_instance(organization_name="Acme", email="admin@example.com", password=password)
        response = api_client.post(
            "/api/setup/",
            {
                "organization_name": "Other",
                "email": "other@example.com",
                "password": password,
            },
        )
        assert response.status_code == 409

    def test_setup_rejects_missing_csrf_token(self, password):
        client = APIClient(enforce_csrf_checks=True)
        client.get("/api/auth/session/")
        response = client.post(
            "/api/setup/",
            {
                "organization_name": "Acme",
                "email": "admin@example.com",
                "password": password,
            },
        )
        assert response.status_code == 403
        assert not is_instance_configured()

    def test_status_polling_does_not_consume_the_post_throttle_quota(
        self, api_client, password, monkeypatch
    ):
        """GET (polled on every /setup page load) and POST (meant to run
        once) must not share a throttle scope, or ordinary page loads could
        exhaust the quota meant to rate-limit the sensitive POST."""
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "setup", "1/min")
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "setup-status", "1000/min")
        cache.clear()

        for _ in range(5):
            status_response = api_client.get("/api/setup/")
            assert status_response.status_code == 200

        response = api_client.post(
            "/api/setup/",
            {
                "organization_name": "Acme",
                "email": "admin@example.com",
                "password": password,
            },
        )
        assert response.status_code == 204
