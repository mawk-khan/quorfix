from apps.core.env import get_choice, get_log_level
from apps.core.log_context import build_logging_config

from .base import *  # noqa: F403

ENVIRONMENT = "development"

DEBUG = True
ALLOWED_HOSTS = ALLOWED_HOSTS or ["localhost", "127.0.0.1", "backend"]  # noqa: F405
CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS or ["http://localhost:3000"]  # noqa: F405
CSRF_TRUSTED_ORIGINS = CSRF_TRUSTED_ORIGINS or ["http://localhost:3000"]  # noqa: F405

# Human-readable by default (base.py's default is "json", meant for
# production) — DEBUG-level so the existing development convention of seeing
# everything locally is unchanged by adding this logging config.
LOG_FORMAT = get_choice("LOG_FORMAT", "plain", ("json", "text", "plain"))
LOG_LEVEL = get_log_level("LOG_LEVEL", "DEBUG")
LOGGING = build_logging_config(log_format=LOG_FORMAT, log_level=LOG_LEVEL)

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Loosened relative to base.py's production-appropriate rates (10/min login,
# etc.) — this module is never used in production (see production.py, which
# inherits only from base.py, not from here), and the Playwright suite in
# frontend/e2e/ runs many sign-ins across its spec files against this exact
# dev server + its real Redis-backed throttle counters within well under a
# minute. At the base rates, the combined suite reliably tripped the "login"
# throttle partway through, causing later specs' legitimate sign-ins to fail
# with what looked like a silent auth failure. This only relaxes rate
# limiting for local development and this test environment.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        # Spread base's rates first so any scope added to base.py in the
        # future (e.g. membership-mutation, demo-mutation) is inherited
        # automatically instead of silently disappearing under dev/CI
        # settings because this dict replaces base's wholesale.
        **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],  # noqa: F405
        "login": "100/min",
        "setup": "100/min",
        "setup-status": "1000/min",
        "invitation-lookup": "100/min",
        "invitation-accept": "100/min",
        # Same loosening rationale as the rates above — real base.py values
        # (20/hour, 30/min) are tuned for production abuse resistance, not
        # for a Playwright suite that creates several invitations/uploads
        # per spec file across dozens of specs within one dev-server run.
        "invitation-create": "100/min",
        "attachment-upload": "300/min",
    },
}
