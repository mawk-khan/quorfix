from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import RequestFactory
from rest_framework.throttling import ScopedRateThrottle

from apps.core.throttling import DemoMutationThrottle

# apps.core.throttling.DemoMutationThrottle — a blanket per-actor throttle
# on mutating requests, inert unless settings.QUORFIX_DEMO_MODE is on. See
# docs/SECURITY.md "Rate limiting". Tested at the throttle-class level
# (not a full HTTP round trip) since what's under test is get_rate()'s
# demo-mode gating and allow_request()'s GET/HEAD/OPTIONS exemption —
# behavior independent of any specific view.


def _request(method, rf):
    request = getattr(rf, method.lower())("/api/bugs/")
    request.user = AnonymousUser()
    return request


class TestDemoMutationThrottleRateGating:
    def test_rate_is_none_when_demo_mode_disabled(self, settings):
        settings.QUORFIX_DEMO_MODE = False
        assert DemoMutationThrottle().get_rate() is None

    def test_rate_reflects_configured_scope_when_demo_mode_enabled(self, settings, monkeypatch):
        settings.QUORFIX_DEMO_MODE = True
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "demo-mutation", "5/min")
        assert DemoMutationThrottle().get_rate() == "5/min"


class TestDemoMutationThrottleBehavior:
    def test_get_requests_are_never_throttled(self, settings, monkeypatch):
        settings.QUORFIX_DEMO_MODE = True
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "demo-mutation", "1/min")
        cache.clear()
        rf = RequestFactory()
        throttle = DemoMutationThrottle()
        for _ in range(5):
            request = _request("get", rf)
            assert throttle.allow_request(request, view=None) is True

    def test_mutating_requests_are_bounded_once_demo_mode_is_enabled(self, settings, monkeypatch):
        settings.QUORFIX_DEMO_MODE = True
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "demo-mutation", "1/min")
        cache.clear()
        rf = RequestFactory()
        throttle = DemoMutationThrottle()
        first = throttle.allow_request(_request("post", rf), view=None)
        second = throttle.allow_request(_request("post", rf), view=None)
        assert first is True
        assert second is False

    def test_mutating_requests_are_unbounded_when_demo_mode_disabled(self, settings):
        settings.QUORFIX_DEMO_MODE = False
        cache.clear()
        rf = RequestFactory()
        throttle = DemoMutationThrottle()
        for _ in range(5):
            request = _request("post", rf)
            assert throttle.allow_request(request, view=None) is True
