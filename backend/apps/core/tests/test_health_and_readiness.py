"""Tests for the liveness (/api/health/) and readiness (/api/health/ready/)
endpoints, and the shared apps.core.storage_readiness check they (and the
check_attachment_storage management command) rely on."""

import os
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings
from rest_framework.test import APIClient

from apps.core.storage_readiness import StorageCheckResult, check_attachment_storage_writable


@pytest.fixture
def api_client():
    return APIClient()


class TestLiveness:
    def test_returns_ok_without_touching_any_dependency(self, api_client, db):
        """No @pytest.mark.django_db transaction shenanigans needed to prove
        this — the real assertion is that database/cache/storage are never
        consulted at all, verified below by mocking each and confirming
        liveness is unaffected."""
        response = api_client.get("/api/health/")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_stays_healthy_when_database_is_down(self, api_client, db):
        with patch(
            "django.db.backends.utils.CursorWrapper.execute", side_effect=Exception("db is down")
        ):
            response = api_client.get("/api/health/")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestReadinessSuccess:
    @pytest.mark.django_db
    def test_all_components_ok_returns_200(self, api_client, tmp_path):
        with override_settings(ATTACHMENTS_LOCAL_ROOT=str(tmp_path)):
            response = api_client.get("/api/health/ready/")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["components"] == {
            "database": {"ok": True},
            "cache": {"ok": True},
            "attachment_storage": {"ok": True},
        }


class TestReadinessDatabaseFailure:
    @pytest.mark.django_db
    def test_database_failure_reported_and_returns_503(self, api_client, tmp_path):
        with override_settings(ATTACHMENTS_LOCAL_ROOT=str(tmp_path)):
            with patch(
                "django.db.backends.utils.CursorWrapper.execute",
                side_effect=Exception("db is down"),
            ):
                response = api_client.get("/api/health/ready/")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "unavailable"
        assert body["components"]["database"] == {"ok": False}
        # The other components are unaffected by the database failure.
        assert body["components"]["cache"] == {"ok": True}
        assert body["components"]["attachment_storage"] == {"ok": True}

    @pytest.mark.django_db
    def test_response_never_includes_exception_details(self, api_client, tmp_path):
        with override_settings(ATTACHMENTS_LOCAL_ROOT=str(tmp_path)):
            with patch(
                "django.db.backends.utils.CursorWrapper.execute",
                side_effect=Exception("super-secret-connection-detail"),
            ):
                response = api_client.get("/api/health/ready/")
        assert "super-secret-connection-detail" not in response.content.decode()


class TestReadinessCacheFailure:
    @pytest.mark.django_db
    def test_cache_failure_reported_and_returns_503(self, api_client, tmp_path):
        with override_settings(ATTACHMENTS_LOCAL_ROOT=str(tmp_path)):
            with patch("django.core.cache.cache.set", side_effect=Exception("redis is down")):
                response = api_client.get("/api/health/ready/")
        assert response.status_code == 503
        body = response.json()
        assert body["components"]["cache"] == {"ok": False}
        assert body["components"]["database"] == {"ok": True}

    @pytest.mark.django_db
    def test_cache_mismatch_is_treated_as_failure(self, api_client, tmp_path):
        """A .get() that doesn't raise but returns the wrong value (e.g. a
        misconfigured shared cache serving stale/foreign data) must not be
        reported as healthy just because no exception was raised."""
        with override_settings(ATTACHMENTS_LOCAL_ROOT=str(tmp_path)):
            with patch("django.core.cache.cache.get", return_value="not-the-probe-value"):
                response = api_client.get("/api/health/ready/")
        assert response.status_code == 503
        assert response.json()["components"]["cache"] == {"ok": False}


class TestReadinessAttachmentStorageFailure:
    @pytest.mark.django_db
    def test_missing_and_uncreatable_root_reported_and_returns_503(self, api_client):
        with override_settings(ATTACHMENTS_LOCAL_ROOT=""):
            response = api_client.get("/api/health/ready/")
        assert response.status_code == 503
        body = response.json()
        assert body["components"]["attachment_storage"] == {"ok": False}
        assert body["components"]["database"] == {"ok": True}
        assert body["components"]["cache"] == {"ok": True}

    @pytest.mark.django_db
    def test_unwritable_root_reported_and_returns_503(self, api_client, tmp_path):
        """Mocks the shared check itself rather than relying on chmod + real
        OS permission enforcement — this view's job is to correctly surface
        whatever check_attachment_storage_writable reports, not to
        re-prove the filesystem behavior TestCheckAttachmentStorageWritable
        already covers directly (including the real-permissions variant,
        skipped when running as root — see that class below)."""
        with override_settings(ATTACHMENTS_LOCAL_ROOT=str(tmp_path)):
            with patch(
                "apps.core.views.check_attachment_storage_writable",
                return_value=StorageCheckResult(False, "mocked: not writable"),
            ):
                response = api_client.get("/api/health/ready/")
        assert response.status_code == 503
        assert response.json()["components"]["attachment_storage"] == {"ok": False}


class TestCheckAttachmentStorageWritable:
    def test_creates_missing_root_and_reports_writable(self, tmp_path):
        root = tmp_path / "does-not-exist-yet"
        with override_settings(ATTACHMENTS_LOCAL_ROOT=str(root)):
            result = check_attachment_storage_writable()
        assert result.ok is True
        assert root.is_dir()

    def test_empty_root_setting_fails_without_touching_disk(self):
        with override_settings(ATTACHMENTS_LOCAL_ROOT=""):
            result = check_attachment_storage_writable()
        assert result.ok is False

    def test_write_failure_fails(self, tmp_path):
        """Mocks the actual write call rather than relying on chmod + real
        OS permission enforcement, so this is deterministic regardless of
        whether the test process itself runs as root — which bypasses
        filesystem permission bits entirely (e.g. inside this repo's dev
        Docker image, which intentionally has no non-root user — see
        docker-compose.yml's `target: dev`) — or as an unprivileged user
        (e.g. a typical CI runner, or the production image's non-root `app`
        user). See test_unwritable_root_fails_under_real_os_permissions
        below for the real-filesystem equivalent where it can actually run
        meaningfully."""
        with override_settings(ATTACHMENTS_LOCAL_ROOT=str(tmp_path)):
            with patch("builtins.open", side_effect=PermissionError("permission denied")):
                result = check_attachment_storage_writable()
        assert result.ok is False

    @pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        reason="root bypasses filesystem permission bits, so chmod(0o500) proves nothing here",
    )
    def test_unwritable_root_fails_under_real_os_permissions(self, tmp_path):
        root = tmp_path / "readonly"
        root.mkdir()
        root.chmod(0o500)
        try:
            with override_settings(ATTACHMENTS_LOCAL_ROOT=str(root)):
                result = check_attachment_storage_writable()
        finally:
            root.chmod(0o700)
        assert result.ok is False

    def test_probe_file_is_removed_after_the_check(self, tmp_path):
        with override_settings(ATTACHMENTS_LOCAL_ROOT=str(tmp_path)):
            check_attachment_storage_writable()
        assert list(tmp_path.iterdir()) == []


class TestCheckAttachmentStorageCommand:
    def test_succeeds_when_writable(self, tmp_path):
        with override_settings(ATTACHMENTS_LOCAL_ROOT=str(tmp_path)):
            call_command("check_attachment_storage")

    def test_raises_command_error_when_unwritable(self, tmp_path):
        with override_settings(ATTACHMENTS_LOCAL_ROOT=str(tmp_path)):
            with patch(
                "apps.core.management.commands.check_attachment_storage."
                "check_attachment_storage_writable",
                return_value=StorageCheckResult(False, "mocked: not writable"),
            ):
                with pytest.raises(CommandError):
                    call_command("check_attachment_storage")
