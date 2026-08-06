"""Request-completion logging (Chunk J §12, optional): one line per request
with method, route template, status, and duration — never the query string
or request body, and never at INFO for the health/readiness probes an
orchestrator may call every few seconds.
"""

from __future__ import annotations

import logging

from apps.core.log_context import monotonic_ms, request_timing_extra

logger = logging.getLogger("apps.core.request")

# Prefix match, not the two exact paths — deliberately covers both
# apps.core.urls routes (health/, health/ready/) under the api/ mount in
# config/urls.py without hardcoding the second one twice.
_HEALTH_PATH_PREFIX = "/api/health"


class RequestLoggingMiddleware:
    """Placed after RequestIdMiddleware (see MIDDLEWARE in
    config/settings/base.py) so the completion line it emits already carries
    the request_id the logging filter reads from that middleware's context.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = monotonic_ms()
        response = self.get_response(request)
        duration_ms = monotonic_ms() - start

        route = getattr(request.resolver_match, "route", None) or request.path
        extra = request_timing_extra(
            method=request.method,
            route=route,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        level = logging.DEBUG if request.path.startswith(_HEALTH_PATH_PREFIX) else logging.INFO
        logger.log(level, "request completed", extra=extra)
        return response
