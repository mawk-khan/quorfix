"""Tests for apps.core.middleware.request_id: generation, validation,
response header echoing, and per-request context isolation."""

import threading

import pytest
from rest_framework.test import APIClient

from apps.core.middleware.request_id import (
    _VALID_REQUEST_ID,
    NO_REQUEST_ID,
    bound_request_id,
    get_request_id,
)


@pytest.fixture
def api_client():
    return APIClient()


class TestGeneratedWhenAbsent:
    def test_response_carries_a_generated_request_id(self, api_client, db):
        response = api_client.get("/api/health/")
        assert response.status_code == 200
        assert response["X-Request-ID"]
        assert _VALID_REQUEST_ID.match(response["X-Request-ID"])

    def test_two_requests_get_different_generated_ids(self, api_client, db):
        first = api_client.get("/api/health/")
        second = api_client.get("/api/health/")
        assert first["X-Request-ID"] != second["X-Request-ID"]


class TestAcceptedWhenValid:
    def test_incoming_valid_id_is_echoed_back_unchanged(self, api_client, db):
        response = api_client.get("/api/health/", HTTP_X_REQUEST_ID="client-supplied-id-123")
        assert response["X-Request-ID"] == "client-supplied-id-123"

    def test_incoming_uuid_shaped_id_is_accepted(self, api_client, db):
        incoming = "550e8400-e29b-41d4-a716-446655440000"
        response = api_client.get("/api/health/", HTTP_X_REQUEST_ID=incoming)
        assert response["X-Request-ID"] == incoming


class TestReplacedWhenInvalid:
    def test_control_characters_are_rejected(self):
        # Django's test client / WSGI layer itself refuses embedded CR/LF in
        # a header value before this middleware ever sees it, so this proves
        # the *validation regex* rejects control characters directly rather
        # than depending on that outer defense.
        assert not _VALID_REQUEST_ID.match("has\tcontrol\x01char")

    def test_oversized_id_is_rejected_and_replaced(self, api_client, db):
        too_long = "a" * 200
        response = api_client.get("/api/health/", HTTP_X_REQUEST_ID=too_long)
        assert response["X-Request-ID"] != too_long
        assert _VALID_REQUEST_ID.match(response["X-Request-ID"])

    def test_disallowed_characters_are_rejected_and_replaced(self, api_client, db):
        response = api_client.get("/api/health/", HTTP_X_REQUEST_ID="has spaces/slashes\\here")
        assert response["X-Request-ID"] != "has spaces/slashes\\here"
        assert _VALID_REQUEST_ID.match(response["X-Request-ID"])

    def test_empty_header_is_treated_as_absent(self, api_client, db):
        response = api_client.get("/api/health/", HTTP_X_REQUEST_ID="")
        assert response["X-Request-ID"]
        assert _VALID_REQUEST_ID.match(response["X-Request-ID"])


class TestContextClearedAfterRequest:
    def test_get_request_id_is_neutral_outside_a_request(self):
        assert get_request_id() == NO_REQUEST_ID

    def test_context_does_not_leak_between_requests_on_the_same_client(self, api_client, db):
        api_client.get("/api/health/", HTTP_X_REQUEST_ID="first-request-id")
        # Nothing outside an active request/response cycle should still see
        # the previous request's ID.
        assert get_request_id() == NO_REQUEST_ID

    def test_exception_response_still_carries_a_request_id(self, api_client, db):
        # A 404 is Django's own well-behaved exception-to-response path
        # (Http404), which still runs entirely inside get_response() and so
        # must still carry the request ID set before it.
        response = api_client.get("/api/nonexistent-route-xyz/")
        assert response.status_code == 404
        assert response["X-Request-ID"]


class TestConcurrentRequestsDoNotLeak:
    def test_context_is_isolated_per_thread(self):
        seen = {}

        def _run(name, value):
            with bound_request_id(value):
                # Cooperative yield point substitute: re-reading immediately
                # after set() on a contextvars.ContextVar, which is
                # thread-local by construction — a leak would show up as
                # another thread's value appearing here.
                seen[name] = get_request_id()

        threads = [threading.Thread(target=_run, args=(f"t{i}", f"id-{i}")) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(10):
            assert seen[f"t{i}"] == f"id-{i}"


class TestBoundRequestId:
    def test_binds_and_restores_previous_value(self):
        assert get_request_id() == NO_REQUEST_ID
        with bound_request_id("inner-id"):
            assert get_request_id() == "inner-id"
        assert get_request_id() == NO_REQUEST_ID

    def test_restores_on_exception(self):
        with pytest.raises(ValueError):
            with bound_request_id("inner-id"):
                raise ValueError("boom")
        assert get_request_id() == NO_REQUEST_ID
