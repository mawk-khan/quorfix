import pytest
from django.test import override_settings


@pytest.mark.django_db
class TestSessionView:
    def test_unauthenticated(self, api_client):
        response = api_client.get("/api/auth/session/")
        assert response.status_code == 200
        assert response.json() == {
            "authenticated": False,
            "user": None,
            "organization": None,
            "role": None,
            "demo_banner": "",
        }

    def test_authenticated_includes_user_organization_and_role(
        self, api_client, admin_user, admin_membership, organization
    ):
        api_client.force_login(admin_user)
        response = api_client.get("/api/auth/session/")
        body = response.json()
        assert body["authenticated"] is True
        assert body["user"]["email"] == admin_user.email
        assert body["organization"]["id"] == str(organization.id)
        assert body["role"] == "administrator"

    def test_seeds_the_csrf_cookie(self, api_client):
        response = api_client.get("/api/auth/session/")
        assert "csrftoken" in response.cookies

    def test_demo_banner_is_empty_by_default(self, api_client):
        response = api_client.get("/api/auth/session/")
        assert response.json()["demo_banner"] == ""

    @override_settings(DEMO_BANNER_MESSAGE="This is a shared demo environment.")
    def test_demo_banner_is_surfaced_when_configured(self, api_client):
        response = api_client.get("/api/auth/session/")
        assert response.json()["demo_banner"] == "This is a shared demo environment."

    @override_settings(DEMO_BANNER_MESSAGE="Demo data may be reset at any time.")
    def test_demo_banner_is_surfaced_for_anonymous_visitors_too(self, api_client):
        # Unauthenticated visitors hit /setup and /sign-in before ever
        # logging in — the "don't enter confidential information" warning
        # is most useful exactly there, not only once already signed in.
        response = api_client.get("/api/auth/session/")
        assert response.json()["demo_banner"] == "Demo data may be reset at any time."
