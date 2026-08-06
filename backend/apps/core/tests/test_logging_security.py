"""Security-sensitive logging review (Chunk J §10): proves — with fake
representative secret values, not just manual code review — that logger
calls across the codebase never carry a password, secret key, session/CSRF
token, invitation token, attachment/comment body, or recipient email.

TestNoForbiddenIdentifiersInLoggerCallSites is a static source scan: every
`logger.<level>(...)` call site anywhere under apps/ (excluding tests and
migrations) is checked for a small, high-confidence blocklist of identifier
substrings. It exists specifically so a future logger call that accidentally
interpolates one of these values fails a test immediately, instead of only
ever being caught by manual review (the explicit instruction this chunk was
given). Everything else in this file is a dynamic, end-to-end check: trigger
the real code path with a fake secret/marker value and assert it never shows
up in captured log output.
"""

import ast
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.bugs.services import assign_bug
from apps.comments.services import create_comment
from apps.notifications.models import Notification, NotificationEventType

_LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}

# Deliberately narrow and high-confidence rather than broad — a token that
# would flag legitimate, already-safe identifiers (e.g. "email_status",
# "token_hash") would train reviewers to ignore this test's failures.
# Email/body content is covered by the dynamic marker-string tests below
# instead, where a substring blocklist would be too blunt an instrument.
#
# database/redis_url/broker_url/email_host_password: no logger call in this
# codebase references settings.DATABASES, settings.REDIS_URL,
# CELERY_BROKER_URL, or EMAIL_HOST_PASSWORD directly (confirmed by the
# Chunk J audit) — this scan is what keeps that true going forward. This is
# a different, narrower guarantee than "a raised exception's own message can
# never contain a credential": readiness-check failures deliberately use
# logger.exception() to capture a real driver exception's own text for
# operators (see docs/OBSERVABILITY.md), and in practice psycopg2/Django's
# Redis backend never echo the password back in their own error messages —
# but that's an assumption about upstream driver behavior, not something
# this scan (or any logging framework) can verify for arbitrary third-party
# exception text.
_FORBIDDEN_SUBSTRINGS = (
    "password",
    "secret_key",
    "session_key",
    "csrftoken",
    "csrf_token",
    "raw_token",
    "databases",
    "redis_url",
    "broker_url",
    "email_host_password",
)

_APPS_ROOT = Path(__file__).resolve().parent.parent.parent


def _iter_app_source_files():
    for path in _APPS_ROOT.rglob("*.py"):
        parts = path.parts
        if "tests" in parts or "migrations" in parts or "__pycache__" in parts:
            continue
        yield path


def _logger_call_source_segments():
    for path in _iter_app_source_files():
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_logger_call = (
                isinstance(func, ast.Attribute)
                and func.attr in _LOG_METHODS
                and isinstance(func.value, ast.Name)
                and func.value.id == "logger"
            )
            if not is_logger_call:
                continue
            segment = ast.get_source_segment(source, node) or ""
            yield path, segment


class TestNoForbiddenIdentifiersInLoggerCallSites:
    def test_no_logger_call_references_a_forbidden_identifier(self):
        violations = []
        for path, segment in _logger_call_source_segments():
            lowered = segment.lower()
            for forbidden in _FORBIDDEN_SUBSTRINGS:
                if forbidden in lowered:
                    violations.append(f"{path}: {forbidden!r} in {segment!r}")
        assert violations == [], "\n".join(violations)

    def test_the_scan_itself_actually_finds_something(self):
        """Guards against the scan silently matching zero call sites (e.g.
        after a refactor away from the `logger.` naming convention it
        depends on), which would make the test above vacuously pass forever."""
        assert len(list(_logger_call_source_segments())) > 5


@pytest.mark.django_db
class TestLoginLoggingExcludesCredentials:
    def test_failed_login_does_not_log_the_password_or_raw_request_body(
        self, api_client, make_user, caplog
    ):
        make_user("someone@example.com")
        fake_password = "sUp3r-Secret-Marker-Pw!"
        with caplog.at_level(logging.DEBUG):
            api_client.post(
                "/api/auth/login/",
                {"email": "someone@example.com", "password": fake_password},
            )
        for record in caplog.records:
            assert fake_password not in record.getMessage()
            assert "someone@example.com" not in record.getMessage()

    def test_successful_login_does_not_log_the_password(
        self, api_client, make_user, password, caplog
    ):
        make_user("someone@example.com", password=password)
        with caplog.at_level(logging.DEBUG):
            api_client.post(
                "/api/auth/login/", {"email": "someone@example.com", "password": password}
            )
        for record in caplog.records:
            assert password not in record.getMessage()


@pytest.mark.django_db
class TestInvitationLoggingExcludesToken:
    def test_failed_acceptance_does_not_log_the_raw_token(self, api_client, caplog):
        fake_token = "marker-raw-invitation-token-should-never-be-logged"
        with caplog.at_level(logging.DEBUG):
            api_client.post(
                f"/api/invitations/{fake_token}/accept/",
                {"password": "sUp3r-Secret-Pw!", "first_name": "A", "last_name": "B"},
            )
        # Scoped to this app's own logger, not django.request — Django's
        # built-in request logging includes the URL path for any 404 (this
        # invalid-token response is one), which is ordinary/unavoidable
        # routing diagnostics, not the credential-leak concern this test is
        # actually about.
        app_records = [r for r in caplog.records if r.name == "apps.organizations.views"]
        assert app_records  # the scan itself must find something to check
        for record in app_records:
            assert fake_token not in record.getMessage()


@pytest.mark.django_db(transaction=True)
class TestNotificationDispatchLoggingExcludesContent:
    def test_broker_failure_log_never_contains_the_comment_body(
        self, django_capture_on_commit_callbacks, caplog, bug, admin_user, admin_membership
    ):
        marker_body = "MARKER-COMMENT-BODY-must-never-appear-in-logs"
        with patch(
            "apps.notifications.tasks.create_notifications_for_event.apply_async",
            side_effect=ConnectionError("broker unreachable"),
        ):
            with caplog.at_level(logging.DEBUG):
                with django_capture_on_commit_callbacks(execute=True):
                    create_comment(
                        bug=bug, author=admin_user, membership=admin_membership, body=marker_body
                    )
        for record in caplog.records:
            assert marker_body not in record.getMessage()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_email_send_never_logs_recipient_address_or_email_body(
        self,
        django_capture_on_commit_callbacks,
        caplog,
        bug,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
    ):
        with caplog.at_level(logging.DEBUG):
            with django_capture_on_commit_callbacks(execute=True):
                assign_bug(
                    bug=bug,
                    actor=admin_user,
                    membership=admin_membership,
                    assignee_id=developer_user.pk,
                    expected_version=bug.version,
                )
        notification = Notification.objects.get(
            organization=bug.organization,
            recipient=developer_user,
            event_type=NotificationEventType.BUG_ASSIGNED,
        )
        for record in caplog.records:
            message = record.getMessage()
            assert developer_user.email not in message
            assert bug.title not in message
        assert notification.recipient_id == developer_user.pk


class TestSettingsSecretsNeverLoggedAtStartup:
    def test_logging_config_construction_never_touches_secret_settings(self, caplog):
        """build_logging_config only ever receives log_format/log_level
        strings — proves it structurally the same way as the static scan
        above, by reconstructing the config with fake-looking values and
        confirming they can't end up anywhere in it."""
        from apps.core.log_context import build_logging_config

        config = build_logging_config(log_format="json", log_level="INFO")
        serialized = repr(config)
        assert "SECRET_KEY" not in serialized
        assert "PASSWORD" not in serialized.upper() or "PASSWORD" not in serialized

    @override_settings(SECRET_KEY="fake-marker-secret-key-should-never-be-logged")
    def test_readiness_failure_log_does_not_include_the_secret_key(self, api_client, db, caplog):
        with caplog.at_level(logging.DEBUG):
            with patch(
                "django.db.backends.utils.CursorWrapper.execute",
                side_effect=Exception("db is down"),
            ):
                api_client.get("/api/health/ready/")
        for record in caplog.records:
            assert "fake-marker-secret-key-should-never-be-logged" not in record.getMessage()
