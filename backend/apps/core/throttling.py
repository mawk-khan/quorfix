from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import UserRateThrottle


class DemoMutationThrottle(UserRateThrottle):
    """Blanket per-actor rate limit on mutating requests, applied ONLY when
    settings.QUORFIX_DEMO_MODE is enabled.

    Completely inert (get_rate() returns None, DRF's own convention for "no
    rate configured" — see ScopedRateThrottle's identical pattern elsewhere
    in this project) on every ordinary Community installation, so it never
    contradicts docs/SECURITY.md's considered, audited decision not to
    throttle bug/comment/project creation for real deployments. Exists
    specifically to bound a public demo's otherwise-deliberately-unthrottled
    mutation-heavy endpoints (bug/comment/project/attachment creation,
    notification actions, etc.) without touching each view individually.

    Keyed by authenticated user (falls back to IP for the rare unauthenticated
    mutation, e.g. invitation-accept) via UserRateThrottle's own
    get_cache_key — a scripted abuse loop can't reset its budget just by
    switching among the five demo personas from the same session/IP, since
    each is a distinct authenticated user with its own bucket; multiplying
    that by pre-authentication persona-switching is still bounded by the
    `login` throttle shared with demo-login.
    """

    scope = "demo-mutation"

    def get_rate(self):
        from django.conf import settings

        if not settings.QUORFIX_DEMO_MODE:
            return None
        return self.THROTTLE_RATES.get(self.scope)

    def allow_request(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return super().allow_request(request, view)
