from apps.core.env import get_choice, get_log_level
from apps.core.log_context import build_logging_config

from .base import *  # noqa: F403

ENVIRONMENT = "test"

DEBUG = False
SECRET_KEY = "test-secret-key"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"

# Plain/readable and quiet by default — pytest's own capture (caplog) reads
# LogRecords directly regardless of formatter, so this only controls what a
# human sees when a test fails and pytest prints captured log output.
# Individual tests that need to assert on INFO/DEBUG-level messages use
# caplog.set_level(...) themselves rather than relying on this default.
LOG_FORMAT = get_choice("LOG_FORMAT", "plain", ("json", "text", "plain"))
LOG_LEVEL = get_log_level("LOG_LEVEL", "WARNING")
LOGGING = build_logging_config(log_format=LOG_FORMAT, log_level=LOG_LEVEL)

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
        "invitation-create": "1000/min",
        "attachment-upload": "1000/min",
        "membership-mutation": "1000/min",
        "demo-mutation": "1000/min",
    },
}

# Local caches (not Redis) so unit tests don't require a running Redis, and
# a per-process cache is fine for the throttle tests that need it.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
