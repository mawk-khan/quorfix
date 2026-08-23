"""Brief maintenance-mode window for apps.core.management.commands.
reset_public_demo — closes the "mutation lands between delete and reseed"
race (see that command's own docstring) without needing per-task
reset-awareness scattered through every service module.

A single shared-cache flag, set for the duration of the reset and checked
by DemoResetInProgressPermission (added to REST_FRAMEWORK's
DEFAULT_PERMISSION_CLASSES). Entirely inert — the permission always allows
the request — unless settings.QUORFIX_DEMO_MODE is on, so this has no
effect whatsoever on an ordinary Community installation.
"""

from __future__ import annotations

from contextlib import contextmanager

from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import APIException
from rest_framework.permissions import SAFE_METHODS, BasePermission

_CACHE_KEY = "quorfix:demo-reset:in-progress"
# Safety net only, not the normal path: if reset_public_demo crashes before
# its own `finally` clears the flag, the demo would otherwise stay
# read-only forever. A real reset finishes in well under this.
_MAX_DURATION_SECONDS = 15 * 60


class DemoResettingError(APIException):
    status_code = 503
    default_detail = "The public demo is briefly resetting. Try again in a moment."
    default_code = "demo_resetting"


@contextmanager
def reset_in_progress():
    """Sets the flag for the duration of the wrapped block, clearing it
    afterward regardless of success/failure. Used by reset_public_demo to
    bracket its own delete-then-reseed phase."""
    cache.set(_CACHE_KEY, True, _MAX_DURATION_SECONDS)
    try:
        yield
    finally:
        cache.delete(_CACHE_KEY)


def is_reset_in_progress() -> bool:
    return bool(cache.get(_CACHE_KEY, False))


class DemoResetInProgressPermission(BasePermission):
    """Rejects mutating requests (POST/PUT/PATCH/DELETE) with 503 while a
    demo reset is in progress. Read requests are never blocked — a briefly
    stale read is preferable to making the whole demo appear down. Always
    True (no-op) unless settings.QUORFIX_DEMO_MODE is enabled."""

    def has_permission(self, request, view) -> bool:
        if not settings.QUORFIX_DEMO_MODE:
            return True
        if request.method in SAFE_METHODS:
            return True
        if is_reset_in_progress():
            raise DemoResettingError()
        return True
