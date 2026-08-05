"""Short-TTL, best-effort caching for dashboard sections.

Dashboard correctness must never depend on Redis being up — cache_or_compute
falls back to calling `compute()` directly (and logs a warning) on any cache
backend failure, on both the read and the write side. Values passed to
`compute()` are always plain, already-shaped dicts/lists (never a lazy
QuerySet), so a cache hit needs no further processing before being returned.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

T = TypeVar("T")


def cache_or_compute(key: str, compute: Callable[[], T], *, ttl: int | None = None) -> T:
    # Read from settings at call time (not a module-level constant) so
    # override_settings(ANALYTICS_CACHE_TTL_SECONDS=...) works in tests.
    ttl = getattr(settings, "ANALYTICS_CACHE_TTL_SECONDS", 60) if ttl is None else ttl

    try:
        cached = cache.get(key)
    except Exception:
        logger.warning(
            "Analytics cache read failed for key %s — computing directly.", key, exc_info=True
        )
        return compute()

    if cached is not None:
        return cached

    value = compute()

    try:
        cache.set(key, value, ttl)
    except Exception:
        logger.warning("Analytics cache write failed for key %s.", key, exc_info=True)

    return value
