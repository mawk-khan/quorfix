import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.core.middleware.admin_login_throttle import _MAX_FAILED_ATTEMPTS

ADMIN_LOGIN_URL = reverse("admin:login")


@pytest.fixture(autouse=True)
def _clear_cache():
    # The throttle counter lives in the shared default cache — never let one
    # test's counter leak into the next.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        username="root", email="root@quorfix.local", password="Correct-Horse-Battery-Staple!"
    )


def _bad_login(client: Client):
    return client.post(ADMIN_LOGIN_URL, {"username": "nobody@quorfix.local", "password": "wrong"})


@pytest.mark.django_db
def test_failed_admin_login_returns_normal_form_response_below_the_limit():
    client = Client()
    response = _bad_login(client)
    assert response.status_code == 200


@pytest.mark.django_db
def test_throttles_after_max_failed_attempts():
    client = Client()
    for _ in range(_MAX_FAILED_ATTEMPTS):
        response = _bad_login(client)
        assert response.status_code == 200

    throttled = _bad_login(client)
    assert throttled.status_code == 429
    assert "Retry-After" in throttled


@pytest.mark.django_db
def test_successful_login_clears_the_failure_count(superuser):
    client = Client()
    for _ in range(_MAX_FAILED_ATTEMPTS - 1):
        assert _bad_login(client).status_code == 200

    success = client.post(
        ADMIN_LOGIN_URL,
        {"username": superuser.email, "password": "Correct-Horse-Battery-Staple!"},
    )
    assert success.status_code == 302

    # The counter was cleared by the successful login — a further failed
    # attempt starts a fresh window rather than immediately tripping 429.
    assert _bad_login(client).status_code == 200


@pytest.mark.django_db
def test_does_not_throttle_get_requests_to_admin_login():
    client = Client()
    for _ in range(_MAX_FAILED_ATTEMPTS + 5):
        response = client.get(ADMIN_LOGIN_URL)
        assert response.status_code == 200


@pytest.mark.django_db
def test_does_not_throttle_unrelated_paths():
    client = Client()
    for _ in range(_MAX_FAILED_ATTEMPTS):
        assert _bad_login(client).status_code == 200

    # The failure count is scoped to /admin/login/ only — ordinary
    # application traffic from the same client is never affected.
    response = client.get("/api/health/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_throttle_is_scoped_per_client_ip():
    attacker = Client(REMOTE_ADDR="10.0.0.1")
    legitimate = Client(REMOTE_ADDR="10.0.0.2")

    for _ in range(_MAX_FAILED_ATTEMPTS):
        assert _bad_login(attacker).status_code == 200
    assert _bad_login(attacker).status_code == 429

    # A different client IP has its own, independent counter.
    assert _bad_login(legitimate).status_code == 200
