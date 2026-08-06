"""Per-request correlation ID: read from an incoming header when it's safe to
trust, otherwise generate one — then make it available for the rest of the
request's lifetime (including exception handling) via a context variable, and
echo it back on the response so a client or reverse proxy can correlate its
own logs against ours.

Deliberately NOT derived from the session or an authenticated user: a request
ID must remain stable and available even for anonymous/unauthenticated
requests (setup, login, health checks) and must never itself be a value that
identifies who made the request.
"""

from __future__ import annotations

import contextlib
import contextvars
import re
import uuid

from django.conf import settings

from apps.core.context import clear_actor_context

# Conservative on purpose: visible ASCII word characters plus '-'/'.' (covers
# a plain UUID4 as well as most upstream-proxy-generated trace IDs), bounded
# length. Excludes CR/LF and control characters implicitly — they simply
# aren't in this character class — so a header value can never be used to
# inject extra lines into a log line or an HTTP response.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

_current_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_request_id", default=None
)

# Neutral fallback for any log line emitted outside a request/response cycle
# (management commands, Celery tasks with no propagated correlation ID,
# app-startup code) — never None, so format strings/filters never need a
# None-check of their own.
NO_REQUEST_ID = "-"


def get_request_id() -> str:
    """The current request's correlation ID, or NO_REQUEST_ID outside any
    request context (or after it has ended)."""
    return _current_request_id.get() or NO_REQUEST_ID


@contextlib.contextmanager
def bound_request_id(value: str):
    """Binds `value` as the current correlation ID for the duration of the
    `with` block. Used outside the HTTP request cycle by
    apps.core.task_correlation to give Celery tasks the same get_request_id()
    plumbing this middleware uses for requests, via the same contextvar."""
    token = _current_request_id.set(value)
    try:
        yield
    finally:
        _current_request_id.reset(token)


def _header_name() -> str:
    return getattr(settings, "REQUEST_ID_HEADER", "X-Request-ID")


def _meta_key(header_name: str) -> str:
    return "HTTP_" + header_name.upper().replace("-", "_")


def _extract_or_generate(request) -> str:
    incoming = request.META.get(_meta_key(_header_name()))
    if incoming and _VALID_REQUEST_ID.match(incoming):
        return incoming
    return uuid.uuid4().hex


class RequestIdMiddleware:
    """Placed immediately after SecurityMiddleware (see MIDDLEWARE in
    config/settings/base.py) — early enough that every other middleware's own
    processing, and any exception raised further down the chain, happens
    inside this request's correlation context."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = _extract_or_generate(request)
        request.request_id = request_id
        token = _current_request_id.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            # Reset (not just overwrite) so a value never leaks into whatever
            # runs next on this worker thread/greenlet — matters under any
            # server model that reuses the running context between requests.
            _current_request_id.reset(token)
            # Owns the actor context's lifecycle even though it never sets
            # it — apps.organizations.authentication binds it mid-request,
            # and clearing it here (rather than there) guarantees it never
            # survives past this request regardless of which branch that
            # authentication code took.
            clear_actor_context()
        response[_header_name()] = request_id
        return response
