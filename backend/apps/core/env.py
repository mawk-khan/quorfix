"""Small, dependency-free environment-variable parsers shared by every
config/settings/*.py module.

Exists specifically to avoid the classic ``bool(os.environ.get(name))``
pitfall — any non-empty string, including the literal ``"false"``, is truthy
in Python — and to give a malformed integer value one consistent, clear
failure at settings-load time instead of a bare ``ValueError`` traceback
pointing into settings-module internals. This failure happens in every
environment (development, test, production) for a genuinely malformed
*type* — a value that parses fine but is merely an unwise choice (e.g. an
unusually large TTL) is a production-only system-check concern instead, see
apps.core.checks.
"""

import os

from django.core.exceptions import ImproperlyConfigured

_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
_FALSE_VALUES = frozenset({"false", "0", "no", "off"})


def get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    # An empty string is treated the same as "unset", not as a malformed
    # value — a `.env` file listing a variable with nothing after the `=`
    # (the documented "leave blank to use the default" convention, e.g.
    # GUNICORN_WORKERS= in .env.example) still sets the key in the
    # container's environment, just with an empty value; os.environ.get
    # alone can't distinguish "absent" from "present but blank", and the
    # latter must fall through to `default` here too.
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ImproperlyConfigured(
        f"{name} must be one of {sorted(_TRUE_VALUES | _FALSE_VALUES)} "
        f"(case-insensitive), got {raw!r}."
    )


def get_list(name: str, default: tuple[str, ...] = ()) -> list[str]:
    raw = os.environ.get(name)
    if raw is None:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        raise ImproperlyConfigured(f"{name} must be an integer, got {raw!r}.") from None


def get_choice(name: str, default: str, choices: tuple[str, ...]) -> str:
    """Validates the raw string against a fixed, hardcoded set of choices —
    never used to build an import path or class name from the environment.
    Case-insensitive; the returned value is always one of `choices` exactly
    as spelled there, never the caller's raw casing."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    for choice in choices:
        if choice.lower() == normalized:
            return choice
    raise ImproperlyConfigured(f"{name} must be one of {choices}, got {raw!r}.")


_VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def get_log_level(name: str, default: str) -> str:
    return get_choice(name, default, _VALID_LOG_LEVELS)
