"""Tests for apps.core.task_correlation: header propagation at dispatch
time, and re-establishing a correlation ID as a task's own logging context
when it runs — independent of any specific business task, using a small
throwaway task defined in this file."""

import logging

import pytest
from celery import shared_task
from django.conf import settings

from apps.core.middleware.request_id import NO_REQUEST_ID, bound_request_id, get_request_id
from apps.core.task_correlation import (
    _CORRELATION_HEADER_KEY,
    correlation_headers,
    task_correlation_context,
)

logger = logging.getLogger(__name__)


class TestWorkerHijackDisabled:
    def test_celery_worker_hijack_root_logger_is_disabled(self):
        """Required, not cosmetic: without this, Celery's own worker
        bootstep reconfigures (hijacks) the root logger with its own
        formatting *after* Django's LOGGING has already set it up — silently
        discarding request_id/environment/service/task_id correlation for
        every task log line. See config/settings/base.py's own comment
        directly above this setting and docs/OBSERVABILITY.md."""
        assert settings.CELERY_WORKER_HIJACK_ROOT_LOGGER is False

    def test_celery_app_actually_reads_it_from_django_settings(self):
        """Guards the wiring, not just the value: config/celery.py's
        app.config_from_object("django.conf:settings", namespace="CELERY")
        must actually resolve CELERY_WORKER_HIJACK_ROOT_LOGGER to Celery's
        own `worker_hijack_root_logger` conf key for the setting above to
        mean anything at all."""
        from config.celery import app as celery_app

        assert celery_app.conf.worker_hijack_root_logger is False


@shared_task(bind=True)
def _probe_task(self):
    """Returns the correlation ID visible inside the task body — the whole
    point under test."""
    with task_correlation_context(self):
        return get_request_id()


class TestCorrelationHeaders:
    def test_empty_outside_any_request(self):
        assert correlation_headers() == {}

    def test_carries_the_bound_request_id(self):
        with bound_request_id("outer-request-id"):
            assert correlation_headers() == {_CORRELATION_HEADER_KEY: "outer-request-id"}

    def test_never_sends_the_neutral_fallback_as_a_value(self):
        assert get_request_id() == NO_REQUEST_ID
        headers = correlation_headers()
        assert _CORRELATION_HEADER_KEY not in headers


class TestHeaderKeyDoesNotCollideWithCeleryInternals:
    """Regression guard for a real bug caught only by a live, non-eager
    dispatch through an actual Redis broker — not by any of the .apply()
    (eager) tests below, which never exhibit it. Celery's own worker-side
    Context class (celery.worker.request.Context) already defines a
    `correlation_id` attribute of its own (unrelated: AMQP's own
    correlation-id property, populated with the task's message id). A
    custom header of that exact name is silently stripped from
    self.request.headers by Context._get_custom_headers() for any task
    actually received over a broker (it survives untouched under
    Task.apply()'s local/eager path, which builds self.request.headers
    differently — hence why only a real end-to-end run caught this)."""

    def test_key_is_not_one_of_celery_context_own_reserved_attributes(self):
        from celery.worker.request import Context

        assert _CORRELATION_HEADER_KEY not in Context.__dict__

    def test_key_survives_the_exact_filtering_a_real_dispatch_applies(self):
        """Reproduces Context._get_custom_headers() directly — the precise
        function responsible for stripping a colliding key — rather than
        requiring a real broker round-trip for this specific regression."""
        from celery.worker.request import Context

        ctx = Context()
        merged = {_CORRELATION_HEADER_KEY: "abc123", "task": "some.task.name", "id": "task-uuid"}
        survived = ctx._get_custom_headers(**merged)
        assert survived == {_CORRELATION_HEADER_KEY: "abc123"}


@pytest.mark.django_db
class TestTaskCorrelationContext:
    def test_propagated_header_is_used_when_present(self):
        result = _probe_task.apply(headers={_CORRELATION_HEADER_KEY: "propagated-id"})
        assert result.get() == "propagated-id"

    def test_generates_its_own_id_when_no_header_is_present(self):
        result = _probe_task.apply()
        correlation_id = result.get()
        assert correlation_id != NO_REQUEST_ID
        assert correlation_id  # non-empty

    def test_two_runs_without_a_header_get_different_generated_ids(self):
        first = _probe_task.apply().get()
        second = _probe_task.apply().get()
        assert first != second

    def test_context_is_cleared_after_the_task_completes(self):
        _probe_task.apply(headers={_CORRELATION_HEADER_KEY: "should-not-leak"})
        assert get_request_id() == NO_REQUEST_ID

    def test_end_to_end_dispatch_propagates_the_current_request_id(self):
        """The combination this whole module exists for: whatever
        correlation_headers() captures at dispatch time is exactly what the
        task sees once it's running, round-tripped through Celery's own
        header mechanism (not a shortcut/mock of it)."""
        with bound_request_id("end-to-end-id"):
            headers = correlation_headers()
        result = _probe_task.apply(headers=headers)
        assert result.get() == "end-to-end-id"
