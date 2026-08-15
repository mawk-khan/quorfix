"""Throttles repeated failed POST /admin/login/ attempts.

Django's classic admin login view is not a DRF view, so ScopedRateThrottle
(REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] in config/settings/base.py) never
covers it — this middleware is the equivalent protection for that one
non-DRF entry point. See docs/SECURITY.md "Rate limiting" for the DRF-side
policy this complements.

This is defense-in-depth, not the primary control: in this project's actual
deployment topology (docker-compose.prod.yml), only the frontend service
publishes a port, and frontend/next.config.ts only rewrites /api/* to the
backend — /admin/ is never proxied through the public edge at all, so it is
already unreachable from the internet by default. This middleware protects
the case where an operator deliberately exposes it anyway (e.g. over a
VPN-only path, or a future change to that topology).

Uses the same shared Redis-backed default cache DRF's throttle counters
already rely on (see CACHES in config/settings/base.py), so the count is
correct across multiple gunicorn workers rather than reset per-process.

Counts only FAILED attempts: Django admin re-renders the login form with
status 200 on bad credentials, and redirects (302/301) on success — so a
legitimate administrator who eventually enters the right password is never
locked out by their own earlier mistakes, and successful admin use is
completely unaffected. Never reads request.POST — nothing here can log or
inspect a submitted password.
"""

from __future__ import annotations

from django.core.cache import cache
from django.http import HttpResponse

ADMIN_LOGIN_PATH = "/admin/login/"

_CACHE_KEY_PREFIX = "admin-login-throttle"
_WINDOW_SECONDS = 300
_MAX_FAILED_ATTEMPTS = 10


def _client_ip(request) -> str:
    # Keyed by IP, so an attacker sharing NAT/IP with a legitimate admin
    # could in principle contribute to that admin's lockout — an accepted
    # tradeoff for a small deployment (see module docstring); the alternative
    # of keying by submitted username would require reading request.POST,
    # which this middleware deliberately never does.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or "unknown"


def _register_failure(key: str) -> None:
    # cache.add only succeeds if the key doesn't exist yet, establishing the
    # window's first count atomically; incr() alone raises ValueError if the
    # key is missing, so add-then-incr (not get-then-set) avoids a lost
    # update between two concurrent failed attempts.
    if not cache.add(key, 1, _WINDOW_SECONDS):
        try:
            cache.incr(key)
        except ValueError:
            # Key expired between the add() above and this incr() — the
            # window has genuinely reset, so start over rather than error.
            cache.set(key, 1, _WINDOW_SECONDS)


class AdminLoginThrottleMiddleware:
    """Placed with the other apps.core middleware in MIDDLEWARE (see
    config/settings/base.py) — order relative to Session/Csrf/Cors doesn't
    matter here, since this only ever inspects request.path/method and the
    final response status, never session or auth state."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path != ADMIN_LOGIN_PATH or request.method != "POST":
            return self.get_response(request)

        key = f"{_CACHE_KEY_PREFIX}:{_client_ip(request)}"
        if (cache.get(key) or 0) >= _MAX_FAILED_ATTEMPTS:
            response = HttpResponse(
                "Too many failed admin sign-in attempts. Try again later.",
                status=429,
                content_type="text/plain",
            )
            response["Retry-After"] = str(_WINDOW_SECONDS)
            return response

        response = self.get_response(request)

        if response.status_code == 200:
            _register_failure(key)
        elif response.status_code in (301, 302):
            cache.delete(key)

        return response
