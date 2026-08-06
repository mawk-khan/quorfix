from .base import *  # noqa: F403

ENVIRONMENT = "test"

DEBUG = False
SECRET_KEY = "test-secret-key"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Generous rates so functional tests aren't cross-contaminated by throttle
# counters accumulating across the test session. Throttling itself has its
# own dedicated tests (test_auth.py, test_setup.py) that don't rely on this.
REST_FRAMEWORK = {  # noqa: F405
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "login": "1000/min",
        "setup": "1000/min",
        "setup-status": "1000/min",
        "invitation-lookup": "1000/min",
        "invitation-accept": "1000/min",
    },
}

# Local caches (not Redis) so unit tests don't require a running Redis, and
# a per-process cache is fine for the throttle tests that need it.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
