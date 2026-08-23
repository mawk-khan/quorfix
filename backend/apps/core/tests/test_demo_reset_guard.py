import pytest
from django.core.cache import cache

from apps.core.demo_reset_guard import (
    DemoResetInProgressPermission,
    is_reset_in_progress,
    reset_in_progress,
)


class _FakeRequest:
    def __init__(self, method: str):
        self.method = method


class TestResetInProgressFlag:
    def test_flag_is_false_by_default(self):
        cache.clear()
        assert is_reset_in_progress() is False

    def test_flag_is_true_inside_the_context_manager(self):
        cache.clear()
        with reset_in_progress():
            assert is_reset_in_progress() is True

    def test_flag_is_cleared_after_the_context_manager_exits(self):
        cache.clear()
        with reset_in_progress():
            pass
        assert is_reset_in_progress() is False

    def test_flag_is_cleared_even_if_the_block_raises(self):
        cache.clear()
        with pytest.raises(ValueError):
            with reset_in_progress():
                raise ValueError("boom")
        assert is_reset_in_progress() is False


class TestDemoResetInProgressPermission:
    def test_inert_when_demo_mode_disabled(self, settings):
        settings.QUORFIX_DEMO_MODE = False
        cache.clear()
        with reset_in_progress():
            permission = DemoResetInProgressPermission()
            assert permission.has_permission(_FakeRequest("POST"), view=None) is True

    def test_get_requests_are_never_blocked(self, settings):
        settings.QUORFIX_DEMO_MODE = True
        cache.clear()
        with reset_in_progress():
            permission = DemoResetInProgressPermission()
            assert permission.has_permission(_FakeRequest("GET"), view=None) is True

    def test_mutating_requests_are_blocked_while_reset_is_in_progress(self, settings):
        from rest_framework.exceptions import APIException

        settings.QUORFIX_DEMO_MODE = True
        cache.clear()
        permission = DemoResetInProgressPermission()
        with reset_in_progress():
            with pytest.raises(APIException) as excinfo:
                permission.has_permission(_FakeRequest("POST"), view=None)
            assert excinfo.value.status_code == 503

    def test_mutating_requests_allowed_once_reset_completes(self, settings):
        settings.QUORFIX_DEMO_MODE = True
        cache.clear()
        with reset_in_progress():
            pass
        permission = DemoResetInProgressPermission()
        assert permission.has_permission(_FakeRequest("POST"), view=None) is True
