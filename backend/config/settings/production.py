import os

from apps.core.env import get_bool, get_int

from .base import *  # noqa: F403

ENVIRONMENT = "production"

# Hardcoded, not environment-derived — DEBUG must never be a value an
# operator can accidentally leave enabled via a stray DJANGO_DEBUG=true in a
# production .env. apps.core.checks.check_debug (quorfix.E002) is a
# structural safety net for this, not the primary control.
DEBUG = False

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Defaults to True — the safe assumption for a backend directly fronted by
# its own dedicated TLS-terminating reverse proxy. docker-compose.prod.yml's
# topology is different: the frontend is the sole edge service (only it
# publishes a port), and the backend is only ever reached over plain HTTP by
# the frontend's internal API proxy and by Celery — both purely internal,
# trusted-Docker-network traffic that never leaves the host. Redirecting
# that internal traffic to HTTPS (which doesn't exist inside the Docker
# network) would break every proxied API call, not just this setting's own
# purpose — so docker-compose.prod.yml explicitly sets
# DJANGO_SECURE_SSL_REDIRECT=false for exactly that reason. This does not
# weaken browser-facing security: SESSION_COOKIE_SECURE/CSRF_COOKIE_SECURE
# above are unaffected (the browser only ever observes whatever protocol the
# operator's own reverse proxy serves the frontend over, never this
# internal hop), and the backend's port is never published, so there is no
# direct-plain-HTTP-to-Django attack surface for this setting to protect
# against in that topology in the first place.
SECURE_SSL_REDIRECT = get_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Assumes TLS terminates at an upstream reverse proxy that forwards the
# standard X-Forwarded-Proto header (nginx, Traefik, Caddy, and most managed
# load balancers all do this by default). Without this, SECURE_SSL_REDIRECT
# above cannot tell an already-HTTPS request forwarded as plain HTTP from a
# genuinely insecure one, and redirect-loops behind the proxy. See
# apps.core.checks.check_https_proxy_header (quorfix.E008).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# apps.core.mail.DemoMailSinkBackend wraps this exact SMTP backend and
# rewrites every message's recipients to QUORFIX_DEMO_MAIL_SINK before
# sending — see that module's docstring and docs/DEMO_DEPLOYMENT.md "Mail
# sink" for why the public demo must never be able to deliver mail to an
# arbitrary external address (e.g. via POST /api/invitations/'s
# admin-issued, attacker-choosable recipient). Inert (identical to today)
# when QUORFIX_DEMO_MODE is false, which is every non-demo deployment.
EMAIL_BACKEND = (
    "apps.core.mail.DemoMailSinkBackend"
    if QUORFIX_DEMO_MODE  # noqa: F405
    else "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = get_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = get_bool("EMAIL_USE_TLS", True)

# Required, non-empty, when QUORFIX_DEMO_MODE is true — validated by
# apps.core.checks.check_email (quorfix.E013). The single mailbox every
# demo-triggered message is redirected to; never a real customer's address.
QUORFIX_DEMO_MAIL_SINK = os.environ.get("QUORFIX_DEMO_MAIL_SINK", "").strip()

# Hashed, compressed filenames (cache-busting) + gzip/brotli precompression,
# resolved from the manifest `collectstatic` writes into STATIC_ROOT at
# image build time (see the Dockerfile's `collectstatic` stage). Only safe
# to use where that manifest is guaranteed to exist — development/test never
# run collectstatic, so they keep Django's plain default storage from
# base.py instead.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
