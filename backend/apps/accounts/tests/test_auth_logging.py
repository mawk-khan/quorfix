"""Chunk J §8/§16: safe login/logout logging — user_id present on success,
no email/password anywhere, request_id always attached via the shared
filter (proven generically in apps.core.tests.test_log_context; here we
only need to confirm these call sites actually emit a record)."""

import logging

import pytest


@pytest.mark.django_db
class TestLoginLogging:
    def test_success_logs_at_info_with_the_users_id(self, api_client, make_user, password, caplog):
        user = make_user("someone@example.com", password=password)
        with caplog.at_level(logging.INFO, logger="apps.accounts.views"):
            api_client.post(
                "/api/auth/login/", {"email": "someone@example.com", "password": password}
            )
        records = [r for r in caplog.records if r.name == "apps.accounts.views"]
        assert any(r.levelno == logging.INFO and "succeeded" in r.getMessage() for r in records)
        info_record = next(r for r in records if r.levelno == logging.INFO)
        assert info_record.user_id == str(user.id)

    def test_failure_logs_a_neutral_warning(self, api_client, make_user, caplog):
        make_user("someone@example.com")
        with caplog.at_level(logging.INFO, logger="apps.accounts.views"):
            api_client.post(
                "/api/auth/login/", {"email": "someone@example.com", "password": "wrong"}
            )
        records = [r for r in caplog.records if r.name == "apps.accounts.views"]
        assert any(r.levelno == logging.WARNING and "failed" in r.getMessage() for r in records)

    def test_failure_for_unknown_email_logs_the_same_neutral_message_as_wrong_password(
        self, api_client, make_user, caplog
    ):
        """Same assertion as test_login_failure_does_not_leak_whether_email_exists
        in test_auth.py, but for the log line instead of the HTTP response —
        the log message text itself must not differ by outcome either."""
        make_user("someone@example.com")
        with caplog.at_level(logging.WARNING, logger="apps.accounts.views"):
            api_client.post(
                "/api/auth/login/", {"email": "someone@example.com", "password": "wrong"}
            )
        wrong_password_messages = [
            r.getMessage() for r in caplog.records if r.name == "apps.accounts.views"
        ]
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="apps.accounts.views"):
            api_client.post(
                "/api/auth/login/", {"email": "nobody@example.com", "password": "wrong"}
            )
        unknown_email_messages = [
            r.getMessage() for r in caplog.records if r.name == "apps.accounts.views"
        ]
        assert wrong_password_messages == unknown_email_messages


@pytest.mark.django_db
class TestLogoutLogging:
    def test_logout_logs_at_info(self, api_client, admin_user, caplog):
        api_client.force_login(admin_user)
        with caplog.at_level(logging.INFO, logger="apps.accounts.views"):
            api_client.post("/api/auth/logout/")
        records = [r for r in caplog.records if r.name == "apps.accounts.views"]
        assert any(r.levelno == logging.INFO and "Logout" in r.getMessage() for r in records)
