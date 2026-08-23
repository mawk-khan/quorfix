"""A single, session-scoped PostgreSQL advisory lock for coordinating a
process-wide, at-most-one operation across containers/processes —
introduced for apps.core.management.commands.reset_public_demo, but
written as a small reusable primitive rather than embedded in that command
directly.

Not a general-purpose locking utility with configurable keys: exactly one
fixed key per named lock, declared as a module-level constant below, so two
unrelated features can never collide on the same integer by accident.
`pg_try_advisory_lock`/`pg_advisory_unlock` are real PostgreSQL functions
(not something Django's ORM wraps) — session-scoped, not transaction-scoped,
so the lock is held across the connection until explicitly released (or the
connection drops), independent of any surrounding transaction.atomic()
commit/rollback.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from django.db import connection

logger = logging.getLogger(__name__)

# Arbitrary, fixed 63-bit signed integers — never derived from a hash at
# runtime (a hash could theoretically collide with some future lock; a
# hardcoded literal cannot silently change). Add new named locks here with
# a new, distinct constant rather than reusing one.
DEMO_RESET_LOCK_KEY = 7_402_918_331_004_552


class LockNotAcquired(Exception):
    """Raised by acquire_lock(blocking=False) when another process already
    holds the lock."""


@contextmanager
def advisory_lock(key: int, *, blocking: bool = False):
    """Context manager around a single PostgreSQL advisory lock.

    blocking=False (the default, and what reset_public_demo always uses):
    tries once, raises LockNotAcquired immediately if another session
    already holds it — never queues behind a concurrent reset, since a
    queued-then-run second reset would just redo the same work
    (idempotently, but pointlessly and confusingly for whoever triggered
    it).
    """
    acquired = False
    with connection.cursor() as cursor:
        if blocking:
            cursor.execute("SELECT pg_advisory_lock(%s)", [key])
            acquired = True
        else:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
            (acquired,) = cursor.fetchone()
        if not acquired:
            raise LockNotAcquired(f"advisory lock {key} is already held by another process")
        try:
            yield
        finally:
            with connection.cursor() as release_cursor:
                release_cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
