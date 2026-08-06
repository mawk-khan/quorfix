"""Structured logging support: a filter that injects request-correlation
fields onto every log record, and formatters that render them consistently.

Nothing here touches the database or the session — RequestContextFilter only
reads already-computed values out of contextvars (apps.core.context,
apps.core.middleware.request_id), matching the constraint that a logging
filter must never trigger I/O of its own.
"""

from __future__ import annotations

import datetime
import json
import logging
import time

from celery import current_task
from django.conf import settings

from apps.core.context import get_organization_id, get_user_id
from apps.core.middleware.request_id import get_request_id

# Fields never to include, even if a caller passes them as a logging `extra`
# kwarg by mistake — a defense-in-depth denylist, not the primary control
# (the primary control is simply never passing these values to a logger call
# anywhere in the codebase). See docs/OBSERVABILITY.md "Sensitive-data policy".
_DENYLIST_FIELDS = frozenset(
    {
        "password",
        "email",
        "session",
        "cookie",
        "csrf_token",
        "token",
        "secret",
        "authorization",
    }
)

_RESERVED_LOGRECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


def _format_timestamp(record: logging.LogRecord) -> str:
    """Microsecond-precision UTC timestamp. Deliberately not
    `Formatter.formatTime(record, "...%f...")` — that delegates to
    `time.strftime`, which (unlike `datetime.strftime`) does not understand
    `%f` and passes it through completely unsubstituted, silently producing
    a literal "%f" in every log line instead of microseconds."""
    dt = datetime.datetime.fromtimestamp(record.created, tz=datetime.UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


class RequestContextFilter(logging.Filter):
    """Attaches request_id/environment/service (always), task_id (only
    inside a running Celery task), and user_id/organization_id (only when
    already bound for the current request) to every LogRecord that passes
    through a handler using this filter."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.environment = getattr(settings, "ENVIRONMENT", "development")
        record.service = getattr(settings, "SERVICE_NAME", "bugfixer-backend")
        record.user_id = get_user_id() or "-"
        record.organization_id = get_organization_id() or "-"
        # current_task is a LocalProxy that resolves to None outside a
        # running task — never raises, never touches the database.
        task = current_task
        record.task_id = getattr(getattr(task, "request", None), "id", None) or "-"
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, even for multi-line tracebacks — the
    traceback text is embedded as a single JSON string field
    (`exc_info`), never interpolated raw into `message`, so a formatted
    exception can never turn one log line into several unparseable ones."""

    def format(self, record: logging.LogRecord) -> str:
        # user_id/organization_id/task_id always present (falling back to
        # "-", same convention as request_id) rather than conditionally
        # omitted — every log line has the same field set, which is what
        # makes a fixed downstream parser/query reliable.
        payload = {
            "timestamp": _format_timestamp(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "task_id": getattr(record, "task_id", "-"),
            "environment": getattr(record, "environment", "-"),
            "service": getattr(record, "service", "-"),
            "user_id": getattr(record, "user_id", "-"),
            "organization_id": getattr(record, "organization_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        for key, value in record.__dict__.items():
            if key in _RESERVED_LOGRECORD_ATTRS or key in payload:
                continue
            if key.lower() in _DENYLIST_FIELDS:
                continue
            try:
                json.dumps(value)
            except TypeError:
                value = str(value)
            payload[key] = value

        return json.dumps(payload, default=str)


class RequestTextFormatter(logging.Formatter):
    """Stable key=value layout for environments that prefer non-JSON
    structured text — every field present on every line, same order,
    always quoted the same way, so it stays greppable/parseable even
    though it isn't JSON."""

    def format(self, record: logging.LogRecord) -> str:
        base = (
            f'timestamp="{_format_timestamp(record)}" '
            f"level={record.levelname} "
            f'logger="{record.name}" '
            f"request_id={getattr(record, 'request_id', '-')} "
            f"task_id={getattr(record, 'task_id', '-')} "
            f"environment={getattr(record, 'environment', '-')} "
            f"service={getattr(record, 'service', '-')} "
            f"user_id={getattr(record, 'user_id', '-')} "
            f"organization_id={getattr(record, 'organization_id', '-')} "
            f'message="{record.getMessage()}"'
        )
        if record.exc_info:
            # Kept on the same logical line via \n replaced only in the
            # embedded traceback text's own internal newlines being left
            # intact would break single-line parsing, so it's appended as
            # its own trailing field instead of interpolated into message.
            exc_text = self.formatException(record.exc_info).replace("\n", " | ")
            base += f' exc_info="{exc_text}"'
        return base


def request_timing_extra(*, method: str, route: str, status_code: int, duration_ms: float) -> dict:
    """Safe fields for a request-completion log line — never the full path
    (query string may carry secrets) or request body."""
    return {
        "http_method": method,
        "http_route": route,
        "http_status": status_code,
        "duration_ms": round(duration_ms, 2),
    }


def monotonic_ms() -> float:
    return time.monotonic() * 1000


def build_logging_config(*, log_format: str, log_level: str) -> dict:
    """Builds Django's LOGGING setting. A single "console" handler on the
    root logger is the only handler anywhere in this config — every other
    logger below is deliberately handler-less with propagate=True, so a
    message is formatted and written exactly once no matter which logger
    emitted it (see docs/OBSERVABILITY.md "Django, Gunicorn, and Celery
    correlation" for why gunicorn.access is deliberately absent from this
    list rather than routed through it).

    log_format selects a fixed, hardcoded formatter key — never used to
    import or construct anything from the environment.
    """
    formatter_name = {"json": "json", "text": "text", "plain": "plain"}[log_format]
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_context": {"()": "apps.core.log_context.RequestContextFilter"},
        },
        "formatters": {
            "json": {"()": "apps.core.log_context.JsonFormatter"},
            "text": {"()": "apps.core.log_context.RequestTextFormatter"},
            "plain": {
                "format": "%(asctime)s %(levelname)-8s %(name)s [%(request_id)s] %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "filters": ["request_context"],
                "formatter": formatter_name,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": log_level,
        },
        "loggers": {
            # Handler-less + propagate=True: forwards to root's single
            # "console" handler instead of using Django's own default
            # handler for these loggers, without creating a second one.
            "django": {"handlers": [], "propagate": True},
            "django.request": {"handlers": [], "propagate": True},
            "django.security": {"handlers": [], "propagate": True},
            "gunicorn.error": {"handlers": [], "propagate": True},
            "celery": {"handlers": [], "propagate": True},
        },
    }
