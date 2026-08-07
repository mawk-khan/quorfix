"""Production-only fail-fast system checks for Quorfix.

Registered from apps.core.apps.CoreConfig.ready() via django.core.checks.register
(with deploy=False, the default, so they run on every plain `manage.py check` —
not only `--deploy`). Every function below is a no-op (returns []) unless
settings.ENVIRONMENT == "production" — see config/settings/{base,development,
test,production}.py for how ENVIRONMENT is set. This is what lets development
and test keep working without ever supplying a production-shaped value, while
production fails loudly and immediately when misconfigured.

Stable check-ID registry (never renumber an existing ID — only append):
    quorfix.E001  DJANGO_SECRET_KEY missing, placeholder, or too short
    quorfix.E002  DEBUG must be False
    quorfix.E003  ALLOWED_HOSTS empty, wildcard, or contains a blank entry
    quorfix.E004  CSRF_TRUSTED_ORIGINS empty, missing scheme, or bare wildcard
    quorfix.E005  CORS misconfiguration (wildcard + credentials, stray "*")
    quorfix.E006  Email backend is console/locmem, or SMTP host is missing
    quorfix.E007  Cookie security flags (Secure/HttpOnly/SameSite) unsafe
    quorfix.E008  SECURE_SSL_REDIRECT enabled without SECURE_PROXY_SSL_HEADER
    quorfix.E009  Database is not PostgreSQL, or name/host is missing
    quorfix.E010  Redis cache/broker URL missing or not a redis(s):// URL
    quorfix.E011  ATTACHMENTS_LOCAL_ROOT missing, relative, or a temp path
    quorfix.E012  ANALYTICS_CACHE_TTL_SECONDS out of the production-sane range

No check here ever includes a secret value (SECRET_KEY, database/SMTP/Redis
passwords) in its message — only the name of the environment variable to set.
"""

from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, Tags, register
from django.core.exceptions import ImproperlyConfigured

_PLACEHOLDER_SECRET_KEYS = frozenset(
    {
        "change-me-to-a-random-secret",  # .env.example
        "test-secret-key",  # config.settings.test
    }
)
MIN_SECRET_KEY_LENGTH = 20

_UNSAFE_PRODUCTION_EMAIL_BACKENDS = frozenset(
    {
        "django.core.mail.backends.console.EmailBackend",
        "django.core.mail.backends.locmem.EmailBackend",
    }
)

_VALID_SAMESITE_VALUES = ("Lax", "Strict")

_TEMP_ROOT_PREFIXES = ("/tmp", "/var/tmp")

MAX_ANALYTICS_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours — a documented, generous upper bound


def _is_production() -> bool:
    return getattr(settings, "ENVIRONMENT", "development") == "production"


def _has_redis_scheme(url: str) -> bool:
    return urlparse(url).scheme in ("redis", "rediss")


def check_secret_key(app_configs, **kwargs):
    if not _is_production():
        return []
    try:
        # Django's own LazySettings.__getattr__ raises ImproperlyConfigured
        # the instant SECRET_KEY is accessed while empty (Django 4.2+) —
        # this is the first thing in the whole process to touch the
        # setting, so it must be caught here rather than left to propagate
        # and crash `manage.py check` with a raw traceback instead of our
        # own clearer, check-ID-carrying error below.
        value = settings.SECRET_KEY or ""
    except ImproperlyConfigured:
        value = ""
    if value.strip() == "":
        return [
            Error(
                "DJANGO_SECRET_KEY is not set. Production requires a unique, "
                "unpredictable secret key — set the DJANGO_SECRET_KEY environment "
                "variable (see .env.example). This message never includes the value.",
                id="quorfix.E001",
            )
        ]
    if value in _PLACEHOLDER_SECRET_KEYS:
        return [
            Error(
                "DJANGO_SECRET_KEY is set to a known development/test placeholder "
                "value. Set DJANGO_SECRET_KEY to a unique, unpredictable value.",
                id="quorfix.E001",
            )
        ]
    if len(value.strip()) < MIN_SECRET_KEY_LENGTH:
        return [
            Error(
                f"DJANGO_SECRET_KEY is shorter than the minimum of "
                f"{MIN_SECRET_KEY_LENGTH} characters expected in production. Set a "
                "longer, unpredictable value.",
                id="quorfix.E001",
            )
        ]
    return []


def check_debug(app_configs, **kwargs):
    if not _is_production():
        return []
    if settings.DEBUG:
        return [
            Error(
                "DEBUG must be False in production — it exposes stack traces, "
                "settings values, and environment details on error pages.",
                id="quorfix.E002",
            )
        ]
    return []


def check_allowed_hosts(app_configs, **kwargs):
    if not _is_production():
        return []
    errors = []
    hosts = settings.ALLOWED_HOSTS
    if not hosts:
        errors.append(
            Error(
                "ALLOWED_HOSTS is empty. Production requires the exact hostname(s) "
                "this instance is served from — set DJANGO_ALLOWED_HOSTS.",
                id="quorfix.E003",
            )
        )
    if "*" in hosts:
        errors.append(
            Error(
                "ALLOWED_HOSTS contains a bare wildcard '*', which accepts the Host "
                "header from any request and defeats Django's Host-header "
                "validation. List explicit hostnames instead.",
                id="quorfix.E003",
            )
        )
    if any(not host.strip() for host in hosts):
        errors.append(
            Error(
                "ALLOWED_HOSTS contains a blank entry — check DJANGO_ALLOWED_HOSTS "
                "for stray commas.",
                id="quorfix.E003",
            )
        )
    return errors


def check_csrf_trusted_origins(app_configs, **kwargs):
    if not _is_production():
        return []
    errors = []
    origins = settings.CSRF_TRUSTED_ORIGINS
    if not origins:
        errors.append(
            Error(
                "CSRF_TRUSTED_ORIGINS is empty. Production requires the exact "
                "origin(s) the frontend is served from — set CSRF_TRUSTED_ORIGINS "
                "(HTTPS is recommended).",
                id="quorfix.E004",
            )
        )
    for origin in origins:
        if origin.strip() == "*":
            errors.append(
                Error(
                    f"CSRF_TRUSTED_ORIGINS entry {origin!r} is a bare wildcard — "
                    "Django requires an explicit scheme and host, e.g. "
                    "https://app.example.com or a scoped subdomain wildcard like "
                    "https://*.example.com.",
                    id="quorfix.E004",
                )
            )
            continue
        parsed = urlparse(origin)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append(
                Error(
                    f"CSRF_TRUSTED_ORIGINS entry {origin!r} must include an explicit "
                    "http:// or https:// scheme and host, e.g. "
                    "https://app.example.com.",
                    id="quorfix.E004",
                )
            )
    return errors


def check_cors(app_configs, **kwargs):
    if not _is_production():
        return []
    errors = []
    allow_all = getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False)
    allow_credentials = getattr(settings, "CORS_ALLOW_CREDENTIALS", False)
    origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])

    if allow_all and allow_credentials:
        errors.append(
            Error(
                "CORS_ALLOW_ALL_ORIGINS is True together with "
                "CORS_ALLOW_CREDENTIALS True. A wildcard origin combined with "
                "credentials lets any website read cookie-authenticated responses "
                "— disable CORS_ALLOW_ALL_ORIGINS or list explicit "
                "CORS_ALLOWED_ORIGINS instead.",
                id="quorfix.E005",
            )
        )
    elif allow_all:
        errors.append(
            Error(
                "CORS_ALLOW_ALL_ORIGINS is True in production. If the frontend is "
                "served same-origin behind the Next.js API proxy (the default "
                "architecture), leave CORS_ALLOWED_ORIGINS empty instead of "
                "allowing all origins; if genuine cross-origin access is needed, "
                "list the exact origins.",
                id="quorfix.E005",
            )
        )
    if "*" in origins:
        errors.append(
            Error(
                "CORS_ALLOWED_ORIGINS contains a literal '*' entry — "
                "django-cors-headers does not treat that as a wildcard in this "
                "list. Use CORS_ALLOW_ALL_ORIGINS for that (subject to the "
                "credentials warning above), or list explicit origins.",
                id="quorfix.E005",
            )
        )
    return errors


def check_email(app_configs, **kwargs):
    if not _is_production():
        return []
    errors = []
    backend = settings.EMAIL_BACKEND
    if backend in _UNSAFE_PRODUCTION_EMAIL_BACKENDS:
        errors.append(
            Error(
                f"EMAIL_BACKEND is {backend!r}, which discards or only logs email "
                "locally instead of delivering it. Configure a real delivery "
                "backend (e.g. django.core.mail.backends.smtp.EmailBackend) for "
                "production.",
                id="quorfix.E006",
            )
        )
    elif backend == "django.core.mail.backends.smtp.EmailBackend":
        if not getattr(settings, "EMAIL_HOST", ""):
            errors.append(
                Error(
                    "EMAIL_BACKEND is the SMTP backend but EMAIL_HOST is not set. "
                    "Set EMAIL_HOST to the SMTP relay's address. (EMAIL_HOST_USER/"
                    "EMAIL_HOST_PASSWORD are not required here — some relays "
                    "authenticate without them.)",
                    id="quorfix.E006",
                )
            )
    return errors


def check_cookies(app_configs, **kwargs):
    if not _is_production():
        return []
    errors = []
    if not settings.SESSION_COOKIE_SECURE:
        errors.append(
            Error(
                "SESSION_COOKIE_SECURE must be True in production so the session "
                "cookie is never sent over plain HTTP.",
                id="quorfix.E007",
            )
        )
    if not settings.CSRF_COOKIE_SECURE:
        errors.append(
            Error(
                "CSRF_COOKIE_SECURE must be True in production so the CSRF cookie "
                "is never sent over plain HTTP.",
                id="quorfix.E007",
            )
        )
    if not settings.SESSION_COOKIE_HTTPONLY:
        errors.append(
            Error(
                "SESSION_COOKIE_HTTPONLY must be True — the session cookie must "
                "never be readable from JavaScript.",
                id="quorfix.E007",
            )
        )
    if settings.SESSION_COOKIE_SAMESITE not in _VALID_SAMESITE_VALUES:
        errors.append(
            Error(
                f"SESSION_COOKIE_SAMESITE is {settings.SESSION_COOKIE_SAMESITE!r}. "
                f"Set it to an explicit 'Lax' or 'Strict' — 'None' (or blank) sends "
                "the cookie cross-site unnecessarily, and this application has no "
                "need for that. This deployment's default is 'Lax' specifically so "
                "an already-signed-in user following an emailed invitation link (a "
                "cross-site top-level navigation) still carries their session "
                "cookie — 'Strict' would block that, so it is deliberately not "
                "hard-required here.",
                id="quorfix.E007",
            )
        )
    if settings.CSRF_COOKIE_SAMESITE not in _VALID_SAMESITE_VALUES:
        errors.append(
            Error(
                f"CSRF_COOKIE_SAMESITE is {settings.CSRF_COOKIE_SAMESITE!r}; must be "
                f"one of {_VALID_SAMESITE_VALUES}.",
                id="quorfix.E007",
            )
        )
    return errors


def check_https_proxy_header(app_configs, **kwargs):
    if not _is_production():
        return []
    if settings.SECURE_SSL_REDIRECT and getattr(settings, "SECURE_PROXY_SSL_HEADER", None) is None:
        return [
            Error(
                "SECURE_SSL_REDIRECT is True but SECURE_PROXY_SSL_HEADER is not "
                "configured. If TLS terminates at an upstream reverse proxy (the "
                "expected production deployment shape), Django cannot tell an "
                "already-HTTPS request forwarded as plain HTTP from a genuinely "
                "insecure one without this header, and will redirect-loop behind "
                "the proxy. Configure SECURE_PROXY_SSL_HEADER to match the header "
                "your proxy sets (commonly "
                "('HTTP_X_FORWARDED_PROTO', 'https')).",
                id="quorfix.E008",
            )
        ]
    return []


def check_database(app_configs, **kwargs):
    if not _is_production():
        return []
    errors = []
    database = settings.DATABASES.get("default", {})
    engine = database.get("ENGINE", "")
    if engine != "django.db.backends.postgresql":
        errors.append(
            Error(
                f"DATABASES['default']['ENGINE'] is {engine!r}. This stack requires "
                "PostgreSQL (django.db.backends.postgresql) in production — SQLite "
                "and other engines are not supported here.",
                id="quorfix.E009",
            )
        )
    if not database.get("NAME"):
        errors.append(
            Error(
                "DATABASES['default']['NAME'] is empty. Set POSTGRES_DB.",
                id="quorfix.E009",
            )
        )
    if not database.get("HOST"):
        errors.append(
            Error(
                "DATABASES['default']['HOST'] is empty. Production expects a "
                "network PostgreSQL service — set POSTGRES_HOST.",
                id="quorfix.E009",
            )
        )
    return errors


def check_redis(app_configs, **kwargs):
    if not _is_production():
        return []
    errors = []
    cache_location = settings.CACHES.get("default", {}).get("LOCATION", "") or ""
    if not cache_location or not _has_redis_scheme(cache_location):
        errors.append(
            Error(
                "The default cache's LOCATION is not a redis:// or rediss:// URL. "
                "Set REDIS_URL — the shared cache backs throttle counters and the "
                "analytics cache, and must be a real Redis instance in production.",
                id="quorfix.E010",
            )
        )
    broker = getattr(settings, "CELERY_BROKER_URL", "") or ""
    if not broker or not _has_redis_scheme(broker):
        errors.append(
            Error(
                "CELERY_BROKER_URL is not a redis:// or rediss:// URL. Set REDIS_URL.",
                id="quorfix.E010",
            )
        )
    # CELERY_RESULT_BACKEND is validated only if set: nothing in this codebase
    # calls .get()/AsyncResult on a task result today, so an empty result
    # backend is not itself an error — only a genuinely malformed one is.
    result_backend = getattr(settings, "CELERY_RESULT_BACKEND", "") or ""
    if result_backend and not _has_redis_scheme(result_backend):
        errors.append(
            Error(
                "CELERY_RESULT_BACKEND is set but is not a redis:// or rediss:// URL.",
                id="quorfix.E010",
            )
        )
    return errors


def check_attachments_root(app_configs, **kwargs):
    if not _is_production():
        return []
    root = settings.ATTACHMENTS_LOCAL_ROOT or ""
    if not root.strip():
        return [
            Error(
                "ATTACHMENTS_LOCAL_ROOT is empty. Set ATTACHMENTS_LOCAL_ROOT to a "
                "persistent, absolute path backed by a durable volume.",
                id="quorfix.E011",
            )
        ]
    if not Path(root).is_absolute():
        return [
            Error(
                f"ATTACHMENTS_LOCAL_ROOT ({root!r}) is not an absolute path. Set it "
                "to an absolute path backed by a durable volume.",
                id="quorfix.E011",
            )
        ]
    if any(root == prefix or root.startswith(prefix + "/") for prefix in _TEMP_ROOT_PREFIXES):
        return [
            Error(
                f"ATTACHMENTS_LOCAL_ROOT ({root!r}) is under a temporary "
                "directory. Uploaded attachments would be lost on reboot or "
                "container recreation — point it at a persistent, durable volume "
                "instead.",
                id="quorfix.E011",
            )
        ]
    return []


def check_analytics_cache_ttl(app_configs, **kwargs):
    if not _is_production():
        return []
    ttl = settings.ANALYTICS_CACHE_TTL_SECONDS
    if not isinstance(ttl, int) or isinstance(ttl, bool):
        return [
            Error(
                f"ANALYTICS_CACHE_TTL_SECONDS ({ttl!r}) is not an integer.",
                id="quorfix.E012",
            )
        ]
    if ttl <= 0:
        return [
            Error(
                f"ANALYTICS_CACHE_TTL_SECONDS ({ttl}) must be greater than zero.",
                id="quorfix.E012",
            )
        ]
    if ttl > MAX_ANALYTICS_CACHE_TTL_SECONDS:
        return [
            Error(
                f"ANALYTICS_CACHE_TTL_SECONDS ({ttl}) exceeds the production-sane "
                f"upper bound of {MAX_ANALYTICS_CACHE_TTL_SECONDS} seconds (24 "
                "hours).",
                id="quorfix.E012",
            )
        ]
    return []


_ALL_CHECKS = (
    check_secret_key,
    check_debug,
    check_allowed_hosts,
    check_csrf_trusted_origins,
    check_cors,
    check_email,
    check_cookies,
    check_https_proxy_header,
    check_database,
    check_redis,
    check_attachments_root,
    check_analytics_cache_ttl,
)


def register_checks() -> None:
    """Called once from apps.core.apps.CoreConfig.ready(). Registered with
    deploy=False (the default) so every check above runs on a plain
    `manage.py check`/`migrate`, not only `--deploy` — production must fail
    before migrations run, not only when an operator remembers --deploy."""
    for check in _ALL_CHECKS:
        register(check, Tags.security)
