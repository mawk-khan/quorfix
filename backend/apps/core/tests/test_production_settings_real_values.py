"""Tests that the *real* config.settings.production module — not a mocked
or override_settings()-constructed stand-in — actually satisfies its own
production checks and carries the exact secure cookie/session values this
project requires.

apps.core.tests.test_environment_checks exercises every apps.core.checks
function directly, but always against synthetic override_settings() values
— it never proves that config/settings/production.py's *actual, committed*
values are what those checks expect. Nothing else in CI does either:
.github/workflows/backend.yml's own `manage.py check` step runs under
DJANGO_SETTINGS_MODULE=config.settings.test, never against production.py
for real. A typo or an accidentally-reverted line in production.py (e.g.
SESSION_COOKIE_SECURE flipped to False) would pass every existing
automated check.

These tests run `manage.py` as a real subprocess with
DJANGO_SETTINGS_MODULE=config.settings.production and a valid, dummy
production-shaped environment — the same manual verification already
documented in docs/BACKUP_AND_RESTORE.md / docs/UPGRADING.md's drills, now
automated. No real secret is used anywhere here.
"""

import json
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent

_VALID_PRODUCTION_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DJANGO_SECRET_KEY": "a-sufficiently-long-unpredictable-dummy-value-for-tests-only-1234567890",
    "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1,backend",
    "CSRF_TRUSTED_ORIGINS": "https://app.example.test",
    "EMAIL_HOST": "smtp.example.test",
    "ATTACHMENTS_LOCAL_ROOT": "/data/attachments",
    "POSTGRES_DB": "quorfix",
    "POSTGRES_USER": "quorfix",
    "POSTGRES_HOST": "db",
    "REDIS_URL": "redis://redis:6379/0",
}


def _run_manage(args: list[str], env_overrides: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    env.update(_VALID_PRODUCTION_ENV)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_real_production_settings_pass_manage_py_check_with_valid_env():
    """The actual, committed config.settings.production module — not a
    synthetic stand-in — must pass every quorfix.E0xx check when given a
    valid production-shaped environment."""
    result = _run_manage(["check"])
    assert result.returncode == 0, (
        f"manage.py check failed against the real production settings module:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_real_production_settings_reject_an_invalid_env():
    """Sanity check on the sanity check: an env this test knows is invalid
    (placeholder secret key) must still fail — proving the test above isn't
    passing merely because checks are silently not running."""
    result = _run_manage(
        ["check"], env_overrides={"DJANGO_SECRET_KEY": "change-me-to-a-random-secret"}
    )
    assert result.returncode != 0
    assert "quorfix.E001" in result.stdout + result.stderr


def _print_real_settings_script() -> str:
    return (
        "import django, json, os\n"
        "django.setup()\n"
        "from django.conf import settings\n"
        "print(json.dumps({\n"
        "    'DEBUG': settings.DEBUG,\n"
        "    'SESSION_COOKIE_SECURE': settings.SESSION_COOKIE_SECURE,\n"
        "    'CSRF_COOKIE_SECURE': settings.CSRF_COOKIE_SECURE,\n"
        "    'SESSION_COOKIE_HTTPONLY': settings.SESSION_COOKIE_HTTPONLY,\n"
        "    'SESSION_COOKIE_SAMESITE': settings.SESSION_COOKIE_SAMESITE,\n"
        "    'CSRF_COOKIE_SAMESITE': settings.CSRF_COOKIE_SAMESITE,\n"
        "    'SECURE_SSL_REDIRECT': settings.SECURE_SSL_REDIRECT,\n"
        "    'SECURE_CONTENT_TYPE_NOSNIFF': settings.SECURE_CONTENT_TYPE_NOSNIFF,\n"
        "    'X_FRAME_OPTIONS': settings.X_FRAME_OPTIONS,\n"
        "    'SESSION_COOKIE_AGE': settings.SESSION_COOKIE_AGE,\n"
        "    'MAX_ATTACHMENT_SIZE_BYTES': settings.MAX_ATTACHMENT_SIZE_BYTES,\n"
        "    'EMAIL_BACKEND': settings.EMAIL_BACKEND,\n"
        "}))\n"
    )


def _real_settings_values(env_overrides: dict | None = None) -> dict:
    import os

    env = dict(os.environ)
    env.update(_VALID_PRODUCTION_ENV)
    if env_overrides:
        env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, "-c", _print_real_settings_script()],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    return json.loads(result.stdout)


def test_real_production_settings_have_exact_expected_cookie_and_security_values():
    """Reads the real, committed values directly off config.settings.production
    (via `python -c`, a separate process — Django only supports one active
    settings module per process) rather than re-deriving them, so a future
    accidental edit to production.py is caught here even if every
    apps.core.checks function were somehow also broken at the same time."""
    values = _real_settings_values()

    assert values["DEBUG"] is False
    assert values["SESSION_COOKIE_SECURE"] is True
    assert values["CSRF_COOKIE_SECURE"] is True
    assert values["SESSION_COOKIE_HTTPONLY"] is True
    # Lax, not Strict: an already-signed-in user following an emailed
    # invitation link (a cross-site top-level navigation) must still carry
    # their session cookie — see backend/config/settings/base.py.
    assert values["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert values["CSRF_COOKIE_SAMESITE"] == "Lax"
    assert values["SECURE_SSL_REDIRECT"] is True
    assert values["SECURE_CONTENT_TYPE_NOSNIFF"] is True
    assert values["X_FRAME_OPTIONS"] == "DENY"
    # Neither demo-only override applies to an ordinary production
    # deployment (QUORFIX_DEMO_MODE unset/false in _VALID_PRODUCTION_ENV) —
    # Django's own two-week session default and the standard 10 MB
    # attachment cap, real SMTP delivery.
    assert values["SESSION_COOKIE_AGE"] == 1209600
    assert values["MAX_ATTACHMENT_SIZE_BYTES"] == 10 * 1024 * 1024
    assert values["EMAIL_BACKEND"] == "django.core.mail.backends.smtp.EmailBackend"


def test_real_production_settings_apply_demo_hardening_when_demo_mode_enabled():
    """Step 3 (public-demo hardening): with QUORFIX_DEMO_MODE=true and a
    valid QUORFIX_DEMO_MAIL_SINK, the real production settings module must
    actually apply the shortened session lifetime, the tightened attachment
    cap, and the mail-sink email backend — and still pass manage.py check
    (proving quorfix.E013 doesn't itself block a correctly-configured demo)."""
    env_overrides = {
        "QUORFIX_DEMO_MODE": "true",
        "QUORFIX_DEMO_MAIL_SINK": "ops@example.test",
    }
    check_result = _run_manage(["check"], env_overrides=env_overrides)
    assert check_result.returncode == 0, (
        f"stdout: {check_result.stdout}\nstderr: {check_result.stderr}"
    )

    values = _real_settings_values(env_overrides)
    assert values["SESSION_COOKIE_AGE"] == 4 * 60 * 60
    assert values["MAX_ATTACHMENT_SIZE_BYTES"] == 2 * 1024 * 1024
    assert values["EMAIL_BACKEND"] == "apps.core.mail.DemoMailSinkBackend"
    # Every other production hardening value is unaffected by demo mode.
    assert values["SESSION_COOKIE_SECURE"] is True
    assert values["DEBUG"] is False


def test_real_production_settings_demo_mode_without_mail_sink_fails_check():
    """Sanity check on the check above: QUORFIX_DEMO_MODE=true with no
    QUORFIX_DEMO_MAIL_SINK must fail manage.py check (quorfix.E013) rather
    than silently booting with mail sent nowhere useful."""
    result = _run_manage(["check"], env_overrides={"QUORFIX_DEMO_MODE": "true"})
    assert result.returncode != 0
    assert "quorfix.E013" in result.stdout + result.stderr
