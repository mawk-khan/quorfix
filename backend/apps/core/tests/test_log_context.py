"""Tests for apps.core.log_context: the request-context logging filter and
the JSON/text formatters built on top of it."""

import json
import logging

from apps.core.context import bind_actor_context, clear_actor_context
from apps.core.log_context import JsonFormatter, RequestContextFilter, RequestTextFormatter
from apps.core.middleware.request_id import bound_request_id


def _make_record(logger_name="apps.somewhere", msg="hello", level=logging.INFO, exc_info=None):
    return logging.LogRecord(
        name=logger_name,
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )


class TestRequestContextFilter:
    def test_fallback_fields_outside_any_request(self):
        record = _make_record()
        RequestContextFilter().filter(record)
        assert record.request_id == "-"
        assert record.user_id == "-"
        assert record.organization_id == "-"
        assert record.task_id == "-"
        assert record.environment  # always set (settings.ENVIRONMENT), never blank
        assert record.service  # always set (settings.SERVICE_NAME), never blank

    def test_request_id_reflects_bound_context(self):
        record = _make_record()
        with bound_request_id("abc-123"):
            RequestContextFilter().filter(record)
        assert record.request_id == "abc-123"

    def test_user_and_organization_id_included_when_bound(self):
        record = _make_record()
        try:
            bind_actor_context(user_id="user-1", organization_id="org-1")
            RequestContextFilter().filter(record)
        finally:
            clear_actor_context()
        assert record.user_id == "user-1"
        assert record.organization_id == "org-1"

    def test_filter_always_returns_true(self):
        assert RequestContextFilter().filter(_make_record()) is True


class TestJsonFormatter:
    def test_produces_valid_single_line_json_with_expected_fields(self):
        record = _make_record(msg="something happened")
        RequestContextFilter().filter(record)
        line = JsonFormatter().format(record)
        assert "\n" not in line
        payload = json.loads(line)
        assert payload["message"] == "something happened"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "apps.somewhere"
        assert payload["request_id"] == "-"
        assert set(payload) >= {
            "timestamp",
            "level",
            "logger",
            "message",
            "request_id",
            "task_id",
            "environment",
            "service",
            "user_id",
            "organization_id",
        }

    def test_multiline_traceback_stays_a_single_json_line(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = _make_record(msg="failed", level=logging.ERROR, exc_info=sys.exc_info())
        RequestContextFilter().filter(record)
        line = JsonFormatter().format(record)
        assert "\n" not in line
        payload = json.loads(line)
        assert "ValueError" in payload["exc_info"]
        assert "boom" in payload["exc_info"]

    def test_extra_fields_are_included(self):
        record = _make_record()
        record.http_status = 200
        record.duration_ms = 12.5
        RequestContextFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))
        assert payload["http_status"] == 200
        assert payload["duration_ms"] == 12.5

    def test_denylisted_extra_field_is_dropped(self):
        record = _make_record()
        record.password = "should-never-appear"
        RequestContextFilter().filter(record)
        line = JsonFormatter().format(record)
        assert "should-never-appear" not in line


class TestRequestTextFormatter:
    def test_produces_stable_key_value_layout(self):
        record = _make_record(msg="something happened")
        RequestContextFilter().filter(record)
        line = RequestTextFormatter().format(record)
        assert "\n" not in line
        assert "level=INFO" in line
        assert 'logger="apps.somewhere"' in line
        assert "request_id=-" in line
        assert 'message="something happened"' in line

    def test_traceback_newlines_collapsed_onto_one_line(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = _make_record(msg="failed", level=logging.ERROR, exc_info=sys.exc_info())
        RequestContextFilter().filter(record)
        line = RequestTextFormatter().format(record)
        assert "\n" not in line
        assert "ValueError" in line
