"""Tests for apps.core.checks — the production-only fail-fast system checks.

Every check function is called directly (not via `manage.py check`) with
django.test.override_settings, so these run fast and without a database.
Each test asserts on stable check IDs (bugfixer.E0xx), not on message
wording, so message copy can be improved later without breaking coverage.
"""

from django.test import override_settings

from apps.core import checks


class TestEnvironmentIdentityGating:
    """No check below may require a production-shaped value outside
    ENVIRONMENT == "production" — this is what lets development and test
    keep working without ever supplying one."""

    @override_settings(ENVIRONMENT="development", SECRET_KEY="", DEBUG=True, ALLOWED_HOSTS=[])
    def test_development_does_not_require_production_values(self):
        assert checks.check_secret_key(None) == []
        assert checks.check_debug(None) == []
        assert checks.check_allowed_hosts(None) == []

    @override_settings(ENVIRONMENT="test", SECRET_KEY="", DEBUG=True, ALLOWED_HOSTS=[])
    def test_test_environment_does_not_require_production_values(self):
        assert checks.check_secret_key(None) == []
        assert checks.check_debug(None) == []
        assert checks.check_allowed_hosts(None) == []

    def test_production_checks_activate_only_when_explicitly_configured(self):
        with override_settings(ENVIRONMENT="production", SECRET_KEY=""):
            assert checks.check_secret_key(None) != []
        with override_settings(ENVIRONMENT="development", SECRET_KEY=""):
            assert checks.check_secret_key(None) == []
        with override_settings(ENVIRONMENT="test", SECRET_KEY=""):
            assert checks.check_secret_key(None) == []


class TestSecretKey:
    @override_settings(ENVIRONMENT="production", SECRET_KEY="")
    def test_missing(self):
        assert [e.id for e in checks.check_secret_key(None)] == ["bugfixer.E001"]

    @override_settings(ENVIRONMENT="production", SECRET_KEY="    ")
    def test_whitespace_only(self):
        assert [e.id for e in checks.check_secret_key(None)] == ["bugfixer.E001"]

    @override_settings(ENVIRONMENT="production", SECRET_KEY="change-me-to-a-random-secret")
    def test_known_placeholder(self):
        assert [e.id for e in checks.check_secret_key(None)] == ["bugfixer.E001"]

    @override_settings(ENVIRONMENT="production", SECRET_KEY="too-short")
    def test_too_short(self):
        assert [e.id for e in checks.check_secret_key(None)] == ["bugfixer.E001"]

    @override_settings(
        ENVIRONMENT="production", SECRET_KEY="a-sufficiently-long-unpredictable-value-1234"
    )
    def test_valid_value(self):
        assert checks.check_secret_key(None) == []


class TestDebug:
    @override_settings(ENVIRONMENT="production", DEBUG=True)
    def test_debug_true_rejected(self):
        assert [e.id for e in checks.check_debug(None)] == ["bugfixer.E002"]

    @override_settings(ENVIRONMENT="production", DEBUG=False)
    def test_debug_false_accepted(self):
        assert checks.check_debug(None) == []


class TestAllowedHosts:
    @override_settings(ENVIRONMENT="production", ALLOWED_HOSTS=[])
    def test_empty_rejected(self):
        assert [e.id for e in checks.check_allowed_hosts(None)] == ["bugfixer.E003"]

    @override_settings(ENVIRONMENT="production", ALLOWED_HOSTS=["*"])
    def test_bare_wildcard_rejected(self):
        assert [e.id for e in checks.check_allowed_hosts(None)] == ["bugfixer.E003"]

    @override_settings(ENVIRONMENT="production", ALLOWED_HOSTS=["app.example.com", "localhost"])
    def test_valid_host_list_including_deliberate_localhost_accepted(self):
        assert checks.check_allowed_hosts(None) == []


class TestCsrfTrustedOrigins:
    @override_settings(ENVIRONMENT="production", CSRF_TRUSTED_ORIGINS=[])
    def test_empty_rejected(self):
        assert [e.id for e in checks.check_csrf_trusted_origins(None)] == ["bugfixer.E004"]

    @override_settings(ENVIRONMENT="production", CSRF_TRUSTED_ORIGINS=["app.example.com"])
    def test_missing_scheme_rejected(self):
        assert [e.id for e in checks.check_csrf_trusted_origins(None)] == ["bugfixer.E004"]

    @override_settings(ENVIRONMENT="production", CSRF_TRUSTED_ORIGINS=["*"])
    def test_bare_wildcard_rejected(self):
        assert [e.id for e in checks.check_csrf_trusted_origins(None)] == ["bugfixer.E004"]

    @override_settings(ENVIRONMENT="production", CSRF_TRUSTED_ORIGINS=["https://app.example.com"])
    def test_valid_https_origin_accepted(self):
        assert checks.check_csrf_trusted_origins(None) == []

    @override_settings(ENVIRONMENT="production", CSRF_TRUSTED_ORIGINS=["https://*.example.com"])
    def test_scoped_wildcard_subdomain_accepted(self):
        assert checks.check_csrf_trusted_origins(None) == []


class TestCors:
    @override_settings(
        ENVIRONMENT="production",
        CORS_ALLOW_ALL_ORIGINS=True,
        CORS_ALLOW_CREDENTIALS=True,
        CORS_ALLOWED_ORIGINS=[],
    )
    def test_wildcard_with_credentials_rejected(self):
        assert [e.id for e in checks.check_cors(None)] == ["bugfixer.E005"]

    @override_settings(
        ENVIRONMENT="production",
        CORS_ALLOW_ALL_ORIGINS=True,
        CORS_ALLOW_CREDENTIALS=False,
        CORS_ALLOWED_ORIGINS=[],
    )
    def test_wildcard_without_credentials_still_rejected(self):
        assert [e.id for e in checks.check_cors(None)] == ["bugfixer.E005"]

    @override_settings(
        ENVIRONMENT="production", CORS_ALLOWED_ORIGINS=["*"], CORS_ALLOW_ALL_ORIGINS=False
    )
    def test_literal_wildcard_string_in_origins_list_rejected(self):
        assert [e.id for e in checks.check_cors(None)] == ["bugfixer.E005"]

    @override_settings(
        ENVIRONMENT="production",
        CORS_ALLOW_ALL_ORIGINS=False,
        CORS_ALLOWED_ORIGINS=[],
        CORS_ALLOW_CREDENTIALS=True,
    )
    def test_same_origin_empty_cors_allowed(self):
        """The Next.js frontend proxies /api/* same-origin, so an empty
        CORS_ALLOWED_ORIGINS is the expected, valid production configuration
        — not an error."""
        assert checks.check_cors(None) == []

    @override_settings(
        ENVIRONMENT="production",
        CORS_ALLOW_ALL_ORIGINS=False,
        CORS_ALLOWED_ORIGINS=["https://third-party-dashboard.example.com"],
    )
    def test_explicit_cross_origin_list_allowed(self):
        assert checks.check_cors(None) == []


class TestEmail:
    @override_settings(
        ENVIRONMENT="production", EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"
    )
    def test_console_backend_rejected(self):
        assert [e.id for e in checks.check_email(None)] == ["bugfixer.E006"]

    @override_settings(
        ENVIRONMENT="production", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    )
    def test_locmem_backend_rejected(self):
        assert [e.id for e in checks.check_email(None)] == ["bugfixer.E006"]

    @override_settings(
        ENVIRONMENT="production",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="",
    )
    def test_smtp_backend_without_host_rejected(self):
        assert [e.id for e in checks.check_email(None)] == ["bugfixer.E006"]

    @override_settings(
        ENVIRONMENT="production",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.com",
    )
    def test_smtp_backend_with_valid_required_settings_accepted(self):
        assert checks.check_email(None) == []

    @override_settings(
        ENVIRONMENT="production",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.com",
        EMAIL_HOST_USER="",
        EMAIL_HOST_PASSWORD="",
    )
    def test_authentication_free_smtp_relay_accepted(self):
        """Some SMTP relays authenticate by source IP/allowlist rather than a
        username/password — this must not be forced to look configured."""
        assert checks.check_email(None) == []


class TestCookies:
    _SAFE_COOKIE_BASE = dict(
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        CSRF_COOKIE_SAMESITE="Lax",
    )

    @override_settings(
        ENVIRONMENT="production", **{**_SAFE_COOKIE_BASE, "SESSION_COOKIE_SECURE": False}
    )
    def test_insecure_session_cookie_rejected(self):
        assert "bugfixer.E007" in [e.id for e in checks.check_cookies(None)]

    @override_settings(
        ENVIRONMENT="production", **{**_SAFE_COOKIE_BASE, "CSRF_COOKIE_SECURE": False}
    )
    def test_insecure_csrf_cookie_rejected(self):
        assert "bugfixer.E007" in [e.id for e in checks.check_cookies(None)]

    @override_settings(
        ENVIRONMENT="production", **{**_SAFE_COOKIE_BASE, "SESSION_COOKIE_HTTPONLY": False}
    )
    def test_non_httponly_session_cookie_rejected(self):
        assert "bugfixer.E007" in [e.id for e in checks.check_cookies(None)]

    @override_settings(ENVIRONMENT="production", **_SAFE_COOKIE_BASE)
    def test_valid_samesite_lax_accepted(self):
        assert checks.check_cookies(None) == []

    @override_settings(
        ENVIRONMENT="production",
        **{
            **_SAFE_COOKIE_BASE,
            "SESSION_COOKIE_SAMESITE": "Strict",
            "CSRF_COOKIE_SAMESITE": "Strict",
        },
    )
    def test_valid_samesite_strict_also_accepted(self):
        """Strict is not the codebase's chosen default (Lax is, for the
        invitation-link flow), but it is still a legitimate, intentional,
        secure choice — the check must not hard-require Lax specifically."""
        assert checks.check_cookies(None) == []

    @override_settings(
        ENVIRONMENT="production", **{**_SAFE_COOKIE_BASE, "SESSION_COOKIE_SAMESITE": "None"}
    )
    def test_invalid_samesite_none_rejected(self):
        assert "bugfixer.E007" in [e.id for e in checks.check_cookies(None)]


class TestHttpsProxyHeader:
    @override_settings(
        ENVIRONMENT="production", SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=None
    )
    def test_ssl_redirect_without_proxy_header_rejected(self):
        assert [e.id for e in checks.check_https_proxy_header(None)] == ["bugfixer.E008"]

    @override_settings(
        ENVIRONMENT="production",
        SECURE_SSL_REDIRECT=True,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    )
    def test_ssl_redirect_with_proxy_header_accepted(self):
        assert checks.check_https_proxy_header(None) == []

    @override_settings(
        ENVIRONMENT="production", SECURE_SSL_REDIRECT=False, SECURE_PROXY_SSL_HEADER=None
    )
    def test_ssl_redirect_disabled_is_not_checked(self):
        assert checks.check_https_proxy_header(None) == []


class TestDatabase:
    @override_settings(
        ENVIRONMENT="production",
        DATABASES={
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "db.sqlite3", "HOST": ""}
        },
    )
    def test_sqlite_rejected(self):
        assert "bugfixer.E009" in [e.id for e in checks.check_database(None)]

    @override_settings(
        ENVIRONMENT="production",
        DATABASES={
            "default": {"ENGINE": "django.db.backends.postgresql", "NAME": "", "HOST": "db"}
        },
    )
    def test_missing_database_name_rejected(self):
        assert "bugfixer.E009" in [e.id for e in checks.check_database(None)]

    @override_settings(
        ENVIRONMENT="production",
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "bugfixer",
                "HOST": "db",
            }
        },
    )
    def test_valid_postgresql_configuration_accepted(self):
        assert checks.check_database(None) == []


class TestRedis:
    @override_settings(
        ENVIRONMENT="production",
        CACHES={"default": {"LOCATION": "not-a-redis-url"}},
        CELERY_BROKER_URL="redis://redis:6379/0",
        CELERY_RESULT_BACKEND="redis://redis:6379/0",
    )
    def test_malformed_cache_url_rejected(self):
        assert "bugfixer.E010" in [e.id for e in checks.check_redis(None)]

    @override_settings(
        ENVIRONMENT="production",
        CACHES={"default": {"LOCATION": "redis://redis:6379/0"}},
        CELERY_BROKER_URL="amqp://guest@rabbit//",
        CELERY_RESULT_BACKEND="redis://redis:6379/0",
    )
    def test_malformed_broker_url_rejected(self):
        assert "bugfixer.E010" in [e.id for e in checks.check_redis(None)]

    @override_settings(
        ENVIRONMENT="production",
        CACHES={"default": {"LOCATION": "redis://redis:6379/0"}},
        CELERY_BROKER_URL="redis://redis:6379/0",
        CELERY_RESULT_BACKEND="redis://redis:6379/0",
    )
    def test_valid_redis_urls_accepted(self):
        assert checks.check_redis(None) == []

    @override_settings(
        ENVIRONMENT="production",
        CACHES={"default": {"LOCATION": "redis://redis:6379/0"}},
        CELERY_BROKER_URL="redis://redis:6379/0",
        CELERY_RESULT_BACKEND="",
    )
    def test_empty_result_backend_is_not_an_error(self):
        """Nothing in this codebase calls .get()/AsyncResult on a task
        result — an empty result backend is not itself a production
        misconfiguration, only a malformed non-empty one is."""
        assert checks.check_redis(None) == []


class TestAttachmentsRoot:
    @override_settings(ENVIRONMENT="production", ATTACHMENTS_LOCAL_ROOT="relative/media")
    def test_relative_root_rejected(self):
        assert [e.id for e in checks.check_attachments_root(None)] == ["bugfixer.E011"]

    @override_settings(ENVIRONMENT="production", ATTACHMENTS_LOCAL_ROOT="/tmp/bugfixer-media")
    def test_temp_root_rejected(self):
        assert [e.id for e in checks.check_attachments_root(None)] == ["bugfixer.E011"]

    @override_settings(ENVIRONMENT="production", ATTACHMENTS_LOCAL_ROOT="")
    def test_empty_root_rejected(self):
        assert [e.id for e in checks.check_attachments_root(None)] == ["bugfixer.E011"]

    @override_settings(ENVIRONMENT="production", ATTACHMENTS_LOCAL_ROOT="/var/lib/bugfixer/media")
    def test_valid_absolute_persistent_path_accepted(self):
        assert checks.check_attachments_root(None) == []


class TestAnalyticsCacheTtl:
    @override_settings(ENVIRONMENT="production", ANALYTICS_CACHE_TTL_SECONDS="60")
    def test_non_integer_type_rejected(self):
        assert [e.id for e in checks.check_analytics_cache_ttl(None)] == ["bugfixer.E012"]

    @override_settings(ENVIRONMENT="production", ANALYTICS_CACHE_TTL_SECONDS=0)
    def test_zero_rejected(self):
        assert [e.id for e in checks.check_analytics_cache_ttl(None)] == ["bugfixer.E012"]

    @override_settings(ENVIRONMENT="production", ANALYTICS_CACHE_TTL_SECONDS=-5)
    def test_negative_rejected(self):
        assert [e.id for e in checks.check_analytics_cache_ttl(None)] == ["bugfixer.E012"]

    @override_settings(
        ENVIRONMENT="production",
        ANALYTICS_CACHE_TTL_SECONDS=checks.MAX_ANALYTICS_CACHE_TTL_SECONDS + 1,
    )
    def test_excessive_value_rejected(self):
        assert [e.id for e in checks.check_analytics_cache_ttl(None)] == ["bugfixer.E012"]

    @override_settings(ENVIRONMENT="production", ANALYTICS_CACHE_TTL_SECONDS=60)
    def test_valid_value_accepted(self):
        assert checks.check_analytics_cache_ttl(None) == []


class TestNoSecretLeakage:
    @override_settings(
        ENVIRONMENT="production",
        SECRET_KEY="",
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": "",
                "HOST": "",
                "PASSWORD": "super-secret-db-password",
            }
        },
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="",
        EMAIL_HOST_PASSWORD="super-secret-smtp-password",
        CACHES={"default": {"LOCATION": "not-a-url-super-secret-redis-password"}},
        CELERY_BROKER_URL="redis://:super-secret-broker-password@redis:6379/0",
    )
    def test_check_messages_never_include_secret_values(self):
        all_errors = (
            checks.check_secret_key(None)
            + checks.check_database(None)
            + checks.check_email(None)
            + checks.check_redis(None)
        )
        combined_text = " ".join(error.msg for error in all_errors)
        assert "super-secret-db-password" not in combined_text
        assert "super-secret-smtp-password" not in combined_text
        assert "super-secret-redis-password" not in combined_text
        assert "super-secret-broker-password" not in combined_text
