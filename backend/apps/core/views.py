import logging

from django.core.cache import cache
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE
from rest_framework.views import APIView

from apps.core.storage_readiness import check_attachment_storage_writable

logger = logging.getLogger(__name__)

_CACHE_PROBE_KEY = "readiness-check-probe"
_CACHE_PROBE_VALUE = "1"


class HealthCheckView(APIView):
    """Liveness probe — answers only "is this process alive and able to
    handle an HTTP request", nothing about its dependencies. Deliberately
    does not touch the database, cache, or attachment storage: an
    orchestrator using this for liveness must not restart an otherwise-fine
    process just because Postgres or Redis had a temporary blip — that is
    exactly what ReadinessCheckView below is for, and it should gate traffic
    routing, not process restarts."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class ReadinessCheckView(APIView):
    """Verifies the service can actually handle a request right now:
    database connectivity, the shared Redis cache, and attachment storage.
    Unlike HealthCheckView, this endpoint is expected to fail when a
    dependency is down — Docker/orchestrator readiness probes should use it
    to stop routing traffic, not to restart the process.

    Every component result is a fixed, safe name plus an ok/not-ok flag
    only — never an exception message, stack trace, connection string, or
    credential. Failure detail goes to the server log, not the response."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        components = {
            "database": self._check_database(),
            "cache": self._check_cache(),
            "attachment_storage": self._check_attachment_storage(),
        }
        overall_ok = all(component["ok"] for component in components.values())
        response_status = HTTP_200_OK if overall_ok else HTTP_503_SERVICE_UNAVAILABLE
        return Response(
            {"status": "ok" if overall_ok else "unavailable", "components": components},
            status=response_status,
        )

    def _check_database(self) -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return {"ok": True}
        except Exception:
            logger.exception("Readiness check: database is unavailable")
            return {"ok": False}

    def _check_cache(self) -> dict:
        try:
            cache.set(_CACHE_PROBE_KEY, _CACHE_PROBE_VALUE, timeout=5)
            value = cache.get(_CACHE_PROBE_KEY)
            cache.delete(_CACHE_PROBE_KEY)
            return {"ok": value == _CACHE_PROBE_VALUE}
        except Exception:
            logger.exception("Readiness check: cache is unavailable")
            return {"ok": False}

    def _check_attachment_storage(self) -> dict:
        result = check_attachment_storage_writable()
        if not result.ok:
            logger.error("Readiness check: attachment storage is unavailable: %s", result.detail)
        return {"ok": result.ok}
