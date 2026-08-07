"""Propagates the current HTTP request's correlation ID into Celery task
headers at dispatch time, and re-establishes a correlation ID as the task's
own logging context while it runs.

Uses Celery's `headers=` mechanism (never a mandatory positional/keyword
task argument) specifically so this never changes any task's call signature
— existing `.delay(...)` call sites that don't pass headers keep working
unchanged, and every dedup/idempotency key derived from a task's own
arguments (see apps.notifications.tasks) is completely unaffected.
"""

from __future__ import annotations

import contextlib
import uuid

from apps.core.middleware.request_id import NO_REQUEST_ID, bound_request_id, get_request_id

# Deliberately NOT "correlation_id" — that name collides with an existing,
# unrelated *built-in* attribute Celery's own worker-side Context class
# already defines (celery.worker.request.Context.correlation_id, part of
# AMQP's own correlation-id property, populated with the task's own message
# id — nothing to do with this project's request correlation). Confirmed by
# a live end-to-end test against a real Redis-backed dispatch (not just
# Task.apply()'s local/eager path, which never exhibited this): Context.
# _get_custom_headers() strips any key matching one of Context's own
# attribute names out of the *nested* self.request.headers dict for a task
# actually received over the broker, so a header named "correlation_id"
# silently vanishes from there specifically for real (non-eager) dispatch —
# while still being reachable as the flattened self.request.correlation_id
# attribute, which is *also* Celery's own reserved slot, so reading it back
# would only coincidentally work and would break the moment Celery's own
# value (or ours) changed shape. A namespaced key sidesteps the collision
# entirely instead of relying on either reading order.
_CORRELATION_HEADER_KEY = "quorfix_correlation_id"


def correlation_headers() -> dict:
    """`headers=` value for `.delay()`/`.apply_async()`. Empty when there is
    no request in progress (e.g. a management command or another task
    dispatching this one) — the task falls back to generating its own
    correlation ID when it runs, rather than carrying a placeholder."""
    request_id = get_request_id()
    if request_id == NO_REQUEST_ID:
        return {}
    return {_CORRELATION_HEADER_KEY: request_id}


def _propagated_correlation_id(task) -> str | None:
    """Reads the header both ways a Context can expose it: the nested
    self.request.headers dict (how Task.apply() — used by every test, and
    internally by apply_async() whenever CELERY_TASK_ALWAYS_EAGER is on —
    always carries it, unfiltered) and the flattened self.request.<key>
    attribute (how a task received over a real broker also carries it,
    alongside the same unfiltered nested dict, since Context.
    _get_custom_headers() only drops names that collide with one of
    Context's own reserved attributes — which _CORRELATION_HEADER_KEY is
    chosen specifically not to).
    """
    headers = getattr(task.request, "headers", None) or {}
    return headers.get(_CORRELATION_HEADER_KEY) or getattr(
        task.request, _CORRELATION_HEADER_KEY, None
    )


@contextlib.contextmanager
def task_correlation_context(task):
    """Binds the executing task's logging correlation ID for the duration of
    the `with` block: the propagated header when the dispatcher provided
    one, otherwise a freshly generated task-local ID so a task triggered by
    a non-HTTP source (retry, another task, Celery beat) still logs under a
    stable ID of its own rather than falling back to "-" for its whole
    execution.
    """
    correlation_id = _propagated_correlation_id(task) or uuid.uuid4().hex
    with bound_request_id(correlation_id):
        yield correlation_id
