import os

from apps.core.env import get_bool, get_int

from .base import *  # noqa: F403

ENVIRONMENT = "production"

# Hardcoded, not environment-derived — DEBUG must never be a value an
# operator can accidentally leave enabled via a stray DJANGO_DEBUG=true in a
# production .env. apps.core.checks.check_debug (bugfixer.E002) is a
# structural safety net for this, not the primary control.
DEBUG = False

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Assumes TLS terminates at an upstream reverse proxy that forwards the
# standard X-Forwarded-Proto header (nginx, Traefik, Caddy, and most managed
# load balancers all do this by default). Without this, SECURE_SSL_REDIRECT
# above cannot tell an already-HTTPS request forwarded as plain HTTP from a
# genuinely insecure one, and redirect-loops behind the proxy. See
# apps.core.checks.check_https_proxy_header (bugfixer.E008).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = get_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = get_bool("EMAIL_USE_TLS", True)
