import pytest


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
