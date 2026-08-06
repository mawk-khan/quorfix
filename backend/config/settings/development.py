from .base import *  # noqa: F403

ENVIRONMENT = "development"

DEBUG = True
ALLOWED_HOSTS = ALLOWED_HOSTS or ["localhost", "127.0.0.1", "backend"]  # noqa: F405
CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS or ["http://localhost:3000"]  # noqa: F405
CSRF_TRUSTED_ORIGINS = CSRF_TRUSTED_ORIGINS or ["http://localhost:3000"]  # noqa: F405

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
        "login": "100/min",
        "setup": "100/min",
        "setup-status": "1000/min",
        "invitation-lookup": "100/min",
        "invitation-accept": "100/min",
    },
}
