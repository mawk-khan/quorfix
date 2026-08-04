import pytest
from django.contrib.auth import authenticate
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle


@pytest.mark.django_db
class TestEmailAuthBackend:
    def test_authenticates_by_email_case_insensitively(self, make_user, password):
        make_user("someone@example.com")
        assert authenticate(email="Someone@Example.com", password=password) is not None

    def test_rejects_wrong_password(self, make_user):
        make_user("someone@example.com")
        assert authenticate(email="someone@example.com", password="wrong") is None

    def test_rejects_unknown_email(self, db, password):
        assert authenticate(email="nobody@example.com", password=password) is None

    def test_rejects_inactive_user(self, make_user, password):
        user = make_user("someone@example.com")
        user.is_active = False
        user.save(update_fields=["is_active"])
        assert authenticate(email="someone@example.com", password=password) is None


@pytest.mark.django_db
class TestLoginView:
    def test_login_success_starts_a_session(self, api_client, make_user, password):
        make_user("someone@example.com")
        response = api_client.post(
            "/api/auth/login/",
            {"email": "someone@example.com", "password": password},
        )
        assert response.status_code == 204
        assert "_auth_user_id" in api_client.session

    def test_login_failure_does_not_leak_whether_email_exists(self, api_client, make_user):
        make_user("someone@example.com")

        wrong_password = api_client.post(
            "/api/auth/login/", {"email": "someone@example.com", "password": "wrong"}
        )
        unknown_email = api_client.post(
            "/api/auth/login/", {"email": "nobody@example.com", "password": "wrong"}
        )

        assert wrong_password.status_code == unknown_email.status_code == 400
        assert wrong_password.json() == unknown_email.json()

    def test_login_rejects_missing_csrf_token(self, make_user, password):
        make_user("someone@example.com")
        client = APIClient(enforce_csrf_checks=True)
        # Seed the CSRF cookie (as the frontend does on every route load) but
        # deliberately don't attach it to this request.
        client.get("/api/auth/session/")

        response = client.post(
            "/api/auth/login/",
            {"email": "someone@example.com", "password": password},
        )
        assert response.status_code == 403

    def test_login_succeeds_with_csrf_token_attached(self, make_user, password):
        make_user("someone@example.com")
        client = APIClient(enforce_csrf_checks=True)
        client.get("/api/auth/session/")
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            "/api/auth/login/",
            {"email": "someone@example.com", "password": password},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 204


@pytest.mark.django_db
class TestLoginThrottling:
    def test_repeated_login_attempts_are_throttled(
        self, api_client, make_user, password, monkeypatch
    ):
        # ScopedRateThrottle.THROTTLE_RATES is resolved from api_settings
        # once at process start (when rest_framework.throttling is first
        # imported) and isn't re-read per request, so override_settings on
        # REST_FRAMEWORK doesn't reach it here. Mutating the dict in place
        # (rather than reassigning it) does, since get_rate() does a fresh
        # dict lookup on every call.
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "login", "1/min")
        # Other tests share this process's cache and the throttle key isn't
        # rate-specific, so a clean slate is needed for a 1/min rate to be
        # meaningful regardless of test execution order.
        cache.clear()
        make_user("someone@example.com")
        first = api_client.post(
            "/api/auth/login/", {"email": "someone@example.com", "password": "wrong"}
        )
        second = api_client.post(
            "/api/auth/login/", {"email": "someone@example.com", "password": password}
        )
        assert first.status_code == 400
        assert second.status_code == 429


@pytest.mark.django_db
class TestLogoutView:
    def test_logout_requires_authentication(self, api_client):
        response = api_client.post("/api/auth/logout/")
        assert response.status_code == 403

    def test_logout_ends_the_session(self, api_client, admin_user):
        api_client.force_login(admin_user)
        response = api_client.post("/api/auth/logout/")
        assert response.status_code == 204
        assert "_auth_user_id" not in api_client.session
