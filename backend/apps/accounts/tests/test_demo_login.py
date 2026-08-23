import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.services import DEMO_ORGANIZATION_SLUG, DEMO_ROLE_TO_EMAIL
from apps.organizations.models import CommunityRole, Organization

DEMO_LOGIN_URL = "/api/auth/demo-login/"


@pytest.fixture
def enable_demo_mode(settings):
    settings.QUORFIX_DEMO_MODE = True


@pytest.fixture
def demo_organization(db):
    return Organization.objects.create(
        name="Quorfix Demo", slug=DEMO_ORGANIZATION_SLUG, is_active=False
    )


@pytest.fixture
def other_organization(db):
    return Organization.objects.create(name="Acme", slug="acme")


@pytest.fixture
def make_demo_persona(demo_organization, make_user, make_membership):
    """Creates a demo persona for `role` at its exact allow-listed email,
    a member of the "quorfix-demo" organization with that same role."""

    def _make(role, *, organization=None, **user_kwargs):
        user = make_user(DEMO_ROLE_TO_EMAIL[role], **user_kwargs)
        make_membership(organization or demo_organization, user, role=role)
        return user

    return _make


@pytest.mark.django_db
class TestDemoLoginDisabled:
    def test_endpoint_unavailable_when_demo_mode_disabled(self, api_client, make_demo_persona):
        make_demo_persona(CommunityRole.DEVELOPER)
        response = api_client.post(DEMO_LOGIN_URL, {"role": "developer"})
        assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.usefixtures("enable_demo_mode")
class TestDemoLoginValidation:
    def test_missing_role_is_rejected(self, api_client):
        response = api_client.post(DEMO_LOGIN_URL, {})
        assert response.status_code == 400

    def test_invalid_role_is_rejected(self, api_client):
        response = api_client.post(DEMO_LOGIN_URL, {"role": "superadmin"})
        assert response.status_code == 400

    def test_arbitrary_email_alone_is_rejected(self, api_client, make_demo_persona):
        make_demo_persona(CommunityRole.ADMINISTRATOR)
        response = api_client.post(DEMO_LOGIN_URL, {"email": "admin@quorfix.local"})
        assert response.status_code == 400
        assert "_auth_user_id" not in api_client.session

    def test_arbitrary_user_id_alone_is_rejected(self, api_client, make_demo_persona):
        user = make_demo_persona(CommunityRole.ADMINISTRATOR)
        response = api_client.post(DEMO_LOGIN_URL, {"user_id": str(user.id)})
        assert response.status_code == 400
        assert "_auth_user_id" not in api_client.session

    def test_extra_fields_are_ignored_not_used_to_pick_the_account(
        self, api_client, make_demo_persona
    ):
        # A supplied "email" alongside a valid "role" must never override
        # which account gets logged in — only the strict role allow-list
        # (apps.accounts.services.DEMO_ROLE_TO_EMAIL) decides that.
        make_demo_persona(CommunityRole.ADMINISTRATOR)
        developer = make_demo_persona(CommunityRole.DEVELOPER)
        response = api_client.post(
            DEMO_LOGIN_URL, {"role": "developer", "email": "admin@quorfix.local"}
        )
        assert response.status_code == 204
        assert str(api_client.session["_auth_user_id"]) == str(developer.id)


@pytest.mark.django_db
@pytest.mark.usefixtures("enable_demo_mode")
class TestDemoLoginSuccess:
    @pytest.mark.parametrize(
        "role",
        [
            CommunityRole.ADMINISTRATOR,
            CommunityRole.DEVELOPER,
            CommunityRole.QA,
            CommunityRole.REPORTER,
            CommunityRole.VIEWER,
        ],
    )
    def test_valid_role_logs_in_the_matching_persona(self, api_client, make_demo_persona, role):
        user = make_demo_persona(role)
        response = api_client.post(DEMO_LOGIN_URL, {"role": role})
        assert response.status_code == 204
        assert str(api_client.session["_auth_user_id"]) == str(user.id)

    def test_resulting_session_matches_normal_login_shape(self, api_client, make_demo_persona):
        make_demo_persona(CommunityRole.DEVELOPER)
        response = api_client.post(DEMO_LOGIN_URL, {"role": "developer"})
        assert response.status_code == 204

        session_response = api_client.get("/api/auth/session/")
        body = session_response.json()
        assert body["authenticated"] is True
        assert body["role"] == "developer"
        assert body["organization"]["slug"] == DEMO_ORGANIZATION_SLUG
        assert body["user"]["email"] == "developer@quorfix.local"

    def test_logout_continues_working_after_demo_login(self, api_client, make_demo_persona):
        make_demo_persona(CommunityRole.VIEWER)
        api_client.post(DEMO_LOGIN_URL, {"role": "viewer"})
        response = api_client.post("/api/auth/logout/")
        assert response.status_code == 204
        assert "_auth_user_id" not in api_client.session

    def test_normal_email_password_login_is_unaffected_by_demo_mode(
        self, api_client, make_user, password
    ):
        make_user("someone@example.com")
        response = api_client.post(
            "/api/auth/login/", {"email": "someone@example.com", "password": password}
        )
        assert response.status_code == 204
        assert "_auth_user_id" in api_client.session


@pytest.mark.django_db
@pytest.mark.usefixtures("enable_demo_mode")
class TestDemoLoginRejections:
    def test_missing_demo_user_is_rejected(self, api_client):
        # Allow-listed role, but no matching account exists in the database
        # at all (e.g. seed_demo was never run).
        response = api_client.post(DEMO_LOGIN_URL, {"role": "administrator"})
        assert response.status_code == 400
        assert "_auth_user_id" not in api_client.session

    def test_inactive_demo_user_is_rejected(self, api_client, make_demo_persona):
        user = make_demo_persona(CommunityRole.QA)
        user.is_active = False
        user.save(update_fields=["is_active"])
        response = api_client.post(DEMO_LOGIN_URL, {"role": "qa"})
        assert response.status_code == 400
        assert "_auth_user_id" not in api_client.session

    def test_user_outside_the_demo_organization_is_rejected(
        self, api_client, make_demo_persona, other_organization
    ):
        # Same allow-listed email, but its membership is in a different
        # organization than "quorfix-demo".
        make_demo_persona(CommunityRole.REPORTER, organization=other_organization)
        response = api_client.post(DEMO_LOGIN_URL, {"role": "reporter"})
        assert response.status_code == 400
        assert "_auth_user_id" not in api_client.session

    def test_membership_role_mismatch_is_rejected(
        self, api_client, make_user, make_membership, demo_organization
    ):
        # The developer persona's email exists in the demo org, but its
        # actual membership role has drifted to "viewer" — the requested
        # role no longer matches reality.
        user = make_user(DEMO_ROLE_TO_EMAIL[CommunityRole.DEVELOPER])
        make_membership(demo_organization, user, role=CommunityRole.VIEWER)
        response = api_client.post(DEMO_LOGIN_URL, {"role": "developer"})
        assert response.status_code == 400
        assert "_auth_user_id" not in api_client.session

    def test_staff_administrator_persona_is_rejected(
        self, api_client, make_user, make_membership, demo_organization
    ):
        # Defense-in-depth: even if the seed data (or a misconfigured
        # deployment) somehow granted the administrator persona Django
        # staff/superuser access, this endpoint must still refuse it.
        user = make_user(DEMO_ROLE_TO_EMAIL[CommunityRole.ADMINISTRATOR])
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        make_membership(demo_organization, user, role=CommunityRole.ADMINISTRATOR)
        response = api_client.post(DEMO_LOGIN_URL, {"role": "administrator"})
        assert response.status_code == 400
        assert "_auth_user_id" not in api_client.session

    def test_superuser_persona_is_rejected(
        self, api_client, make_user, make_membership, demo_organization
    ):
        user = make_user(DEMO_ROLE_TO_EMAIL[CommunityRole.ADMINISTRATOR])
        user.is_superuser = True
        user.save(update_fields=["is_superuser"])
        make_membership(demo_organization, user, role=CommunityRole.ADMINISTRATOR)
        response = api_client.post(DEMO_LOGIN_URL, {"role": "administrator"})
        assert response.status_code == 400
        assert "_auth_user_id" not in api_client.session


@pytest.mark.django_db
@pytest.mark.usefixtures("enable_demo_mode")
class TestDemoLoginCsrf:
    def test_rejects_missing_csrf_token(self, make_demo_persona):
        make_demo_persona(CommunityRole.ADMINISTRATOR)
        client = APIClient(enforce_csrf_checks=True)
        client.get("/api/auth/session/")
        response = client.post(DEMO_LOGIN_URL, {"role": "administrator"})
        assert response.status_code == 403

    def test_succeeds_with_csrf_token_attached(self, make_demo_persona):
        make_demo_persona(CommunityRole.ADMINISTRATOR)
        client = APIClient(enforce_csrf_checks=True)
        client.get("/api/auth/session/")
        csrf_token = client.cookies["csrftoken"].value
        response = client.post(
            DEMO_LOGIN_URL, {"role": "administrator"}, HTTP_X_CSRFTOKEN=csrf_token
        )
        assert response.status_code == 204


@pytest.mark.django_db
@pytest.mark.usefixtures("enable_demo_mode")
class TestDemoLoginThrottling:
    def test_repeated_demo_login_attempts_are_throttled(
        self, api_client, make_demo_persona, monkeypatch
    ):
        # Shares LoginView's "login" scope — see DemoLoginView's docstring.
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "login", "1/min")
        cache.clear()
        make_demo_persona(CommunityRole.ADMINISTRATOR)
        first = api_client.post(DEMO_LOGIN_URL, {"role": "superadmin"})
        second = api_client.post(DEMO_LOGIN_URL, {"role": "administrator"})
        assert first.status_code == 400
        assert second.status_code == 429


@pytest.mark.django_db
@pytest.mark.usefixtures("enable_demo_mode")
class TestDemoLoginNoCredentialLeakage:
    def test_no_password_in_success_response(self, api_client, make_demo_persona, password):
        make_demo_persona(CommunityRole.ADMINISTRATOR)
        response = api_client.post(DEMO_LOGIN_URL, {"role": "administrator"})
        assert password not in response.content.decode()
        assert b"password" not in response.content.lower()

    def test_no_password_in_failure_response(self, api_client):
        response = api_client.post(DEMO_LOGIN_URL, {"role": "administrator"})
        assert b"password" not in response.content.lower()

    def test_no_password_in_session_response_after_demo_login(self, api_client, make_demo_persona):
        make_demo_persona(CommunityRole.VIEWER)
        api_client.post(DEMO_LOGIN_URL, {"role": "viewer"})
        response = api_client.get("/api/auth/session/")
        assert b"password" not in response.content.lower()
