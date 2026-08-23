import os
from pathlib import Path

from apps.core.env import get_bool, get_choice, get_int, get_list, get_log_level
from apps.core.log_context import build_logging_config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Product-facing name — a plain constant, not an environment variable: this
# is static branding (Phase 6 Chunk K), not per-deployment configuration, so
# it doesn't need the indirection get_bool/get_choice's env-driven siblings
# use. Referenced anywhere the backend needs to say the product's name in
# something a user reads (invitation email subject, OpenAPI docs title) —
# see docs/OBSERVABILITY.md's SERVICE_NAME for the separate, *operational*
# (log/process) name, which stays environment-configurable on purpose.
PRODUCT_NAME = "Quorfix"

# Safe fallback only — every concrete settings module (development/test/
# production) sets this explicitly to its own literal value below, so this
# is only ever consulted if a future settings module forgets to. It must
# never resolve to "production" by accident (e.g. via a stray ENVIRONMENT
# env var), so it deliberately does NOT read from the environment.
ENVIRONMENT = "development"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = get_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = get_list("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.organizations",
    "apps.projects",
    "apps.bugs",
    "apps.comments",
    "apps.attachments",
    "apps.activities",
    "apps.notifications",
    "apps.workflows",
    "apps.analytics",
    "apps.integrations",
    "apps.licensing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Immediately after SecurityMiddleware and before everything else, so a
    # request ID is established before any other middleware runs and stays
    # available for the exception-logging that happens inside get_response()
    # further down the chain — see apps.core.middleware.request_id.
    "apps.core.middleware.request_id.RequestIdMiddleware",
    # Optional (Chunk J §12) request-completion timing log — placed
    # immediately after RequestIdMiddleware so its log line already carries
    # the request_id that middleware establishes.
    "apps.core.middleware.request_logging.RequestLoggingMiddleware",
    # Defense-in-depth brute-force throttle for POST /admin/login/ — Django's
    # classic admin login isn't a DRF view, so the ScopedRateThrottle rates
    # below never cover it. See apps.core.middleware.admin_login_throttle for
    # why this is defense-in-depth rather than the primary control.
    "apps.core.middleware.admin_login_throttle.AdminLoginThrottleMiddleware",
    # Serves STATIC_ROOT directly from the WSGI process — there is no
    # separate reverse proxy or CDN in front of gunicorn in this cloud-
    # neutral setup. Harmless in development/test too: it only serves files
    # that exist under STATIC_ROOT and falls through otherwise, and
    # STATIC_ROOT is only ever populated by `collectstatic`, which nothing
    # in dev/test runs. Immediately after SecurityMiddleware per WhiteNoise's
    # own documented placement.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "quorfix"),
        "USER": os.environ.get("POSTGRES_USER", "quorfix"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailAuthBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# ScopedRateThrottle counters live in the default cache. Without a shared
# backend, each app-server process has its own counter and the effective
# rate limit becomes configured_rate * worker_count.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
# Without this, celery's own worker bootstep reconfigures (hijacks) the root
# logger with its own formatting after Django's LOGGING (below) has already
# configured it — silently discarding request_id/environment/service
# correlation for every task log line. See docs/OBSERVABILITY.md.
CELERY_WORKER_HIJACK_ROOT_LOGGER = False

# -- Observability (Phase 6 Chunk J) -----------------------------------------
#
# SERVICE_NAME/REQUEST_ID_HEADER have safe, always-valid defaults — no
# environment can leave these unset. LOG_FORMAT/LOG_LEVEL are validated
# against a fixed, hardcoded set of choices (get_choice/get_log_level raise
# ImproperlyConfigured on anything else) — never used to import or construct
# a class from an arbitrary environment string. See docs/OBSERVABILITY.md.
SERVICE_NAME = os.environ.get("SERVICE_NAME", "quorfix-backend")
REQUEST_ID_HEADER = os.environ.get("REQUEST_ID_HEADER", "X-Request-ID")
LOG_FORMAT = get_choice("LOG_FORMAT", "json", ("json", "text", "plain"))
LOG_LEVEL = get_log_level("LOG_LEVEL", "INFO")
LOGGING = build_logging_config(log_format=LOG_FORMAT, log_level=LOG_LEVEL)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.organizations.authentication.OrganizationAwareSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.BoundedPageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
        # Demo-only blanket mutation throttle — inert (no-op) unless
        # QUORFIX_DEMO_MODE is on; see apps.core.throttling.DemoMutationThrottle
        # for why this is layered on top of (never a replacement for) the
        # scoped throttles below.
        "apps.core.throttling.DemoMutationThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "setup": "3/hour",
        "setup-status": "60/min",
        "invitation-lookup": "30/min",
        "invitation-accept": "10/min",
        # Chunk G additions — see docs/SECURITY.md "Rate limiting" for the
        # full decision. invitation-create: an administrator-only action
        # that sends email to an address the admin doesn't have to own —
        # grouped with the other invitation/auth endpoints above rather
        # than left unthrottled. attachment-upload: shared by both halves
        # of an upload (initiate + upload-bytes) — bounds how fast a
        # single account can fill the local attachment volume; generous
        # enough for a normal multi-file drag-and-drop (up to 30 files/min)
        # while still meaningfully slowing a scripted disk-fill attempt.
        # Bug/comment creation deliberately have no throttle — see
        # docs/SECURITY.md for why.
        "invitation-create": "20/hour",
        "attachment-upload": "30/min",
        # Public-demo hardening additions — see docs/SECURITY.md "Rate
        # limiting". membership-mutation applies unconditionally (a
        # genuine, previously-unthrottled gap independent of demo mode —
        # role changes/removals are inherently rare administrative actions,
        # so this doesn't affect normal use). demo-mutation is read only by
        # apps.core.throttling.DemoMutationThrottle, which ignores this
        # value entirely unless QUORFIX_DEMO_MODE is on.
        "membership-mutation": "30/min",
        "demo-mutation": "40/min",
    },
}

# Instance setup / invitations
INVITATION_EXPIRY_DAYS = 7
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:3000")

# Optional site-wide notice (e.g. "This is a shared demo environment — data
# may be reset and is visible to other demo users. Do not enter confidential
# information."), surfaced via SessionView/SessionSerializer and rendered by
# the frontend's AppShell. Empty by default — a normal/private installation
# shows nothing unless an operator deliberately sets this. Plain text only;
# the frontend renders it as text, never as HTML.
DEMO_BANNER_MESSAGE = os.environ.get("DEMO_BANNER_MESSAGE", "").strip()

# Demo-only "Quick Access" role login (apps.accounts.views.DemoLoginView,
# apps.accounts.services.resolve_demo_login_user) — lets a public demo
# visitor sign in as one of five fixed Community personas without ever
# touching a password. Defaults False and MUST stay False for an ordinary
# Community installation; only a dedicated, disposable public demo
# deployment (e.g. demo.quorfix.com — see docs/DEMO_DEPLOYMENT.md) sets this
# to true. Surfaced to the frontend via SessionSerializer's `demo_mode`
# field (same session-response pattern as DEMO_BANNER_MESSAGE above) rather
# than a NEXT_PUBLIC_* build-time variable, so toggling it never requires a
# frontend rebuild — only restarting the backend with the new value.
QUORFIX_DEMO_MODE = get_bool("QUORFIX_DEMO_MODE", False)

# A public, shared demo session living for Django's default two weeks
# (SESSION_COOKIE_AGE's own default) is needlessly long-lived for a
# throwaway exploration session on a shared machine/browser — shortened to
# a few hours only when QUORFIX_DEMO_MODE is on. Unset (Django's default)
# for every ordinary installation, matching every other demo-only setting
# here.
if QUORFIX_DEMO_MODE:
    SESSION_COOKIE_AGE = get_int("QUORFIX_DEMO_SESSION_COOKIE_AGE_SECONDS", 4 * 60 * 60)

# Comments: how long after posting an author may still edit/delete their own
# comment. Administrators are not bound by this window.
COMMENT_EDIT_WINDOW_MINUTES = 15

# Attachments. Only a local storage backend exists so far (see
# apps.attachments.providers) — an S3-compatible provider is a future addition,
# not a setting to pre-declare here until it actually exists.
#
# The root is the general local media root, NOT an attachments-specific
# subfolder: apps.attachments.services._build_storage_key already prefixes
# every key with "attachments/" (organization/bug/attachment-id/extension —
# a scheme meant to work the same way inside a future S3 bucket, where
# "attachments/" would be one prefix among possibly several). Rooting here at
# .../media/attachments too would nest an "attachments/attachments/..." path.
# Tightened for the public demo (2 MB instead of 10 MB) — a shared,
# anonymous-reachable instance has a much smaller reasonable disk/bandwidth
# budget per upload than a trusted internal deployment; every other
# attachment protection (content-type allowlist, magic-byte verification,
# server-generated storage keys — see apps.attachments.validators) is
# unchanged and applies identically either way. QUORFIX_DEMO_MODE-only;
# every ordinary installation keeps the original 10 MB limit.
MAX_ATTACHMENT_SIZE_BYTES = (
    get_int("QUORFIX_DEMO_MAX_ATTACHMENT_SIZE_BYTES", 2 * 1024 * 1024)
    if QUORFIX_DEMO_MODE
    else 10 * 1024 * 1024
)
ATTACHMENTS_LOCAL_ROOT = os.environ.get("ATTACHMENTS_LOCAL_ROOT", str(BASE_DIR / "media"))

# Email (invitations). Backend and SMTP credentials are set per-environment.
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "webmaster@localhost")

# Analytics dashboard. Short-TTL only (see apps.analytics.caching) — no
# event-driven invalidation. A Redis outage falls back to direct queries
# rather than failing the dashboard.
ANALYTICS_CACHE_TTL_SECONDS = get_int("ANALYTICS_CACHE_TTL_SECONDS", 60)

SPECTACULAR_SETTINGS = {
    "TITLE": f"{PRODUCT_NAME} API",
    "DESCRIPTION": f"{PRODUCT_NAME} Community REST API",
    # Deliberately independent of the product release version (VERSION file
    # / docs/RELEASING.md) — this is the OpenAPI *schema's* own version, and
    # this project has never introduced a breaking API-shape change that
    # would warrant bumping it; see docs/RELEASING.md if that ever changes.
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # drf-spectacular's own default is AllowAny — that would let an
    # unauthenticated internet visitor freely browse the complete API
    # surface (every endpoint, field, and parameter shape) at /api/schema/
    # and /api/docs/. Matches this project's own REST_FRAMEWORK
    # DEFAULT_PERMISSION_CLASSES default below instead, so schema/docs
    # require the same sign-in as the rest of the API rather than being the
    # one anonymous-accessible exception to it.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
}

CORS_ALLOWED_ORIGINS = get_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = get_list("CSRF_TRUSTED_ORIGINS")

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
