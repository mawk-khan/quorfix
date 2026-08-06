"""Gunicorn configuration for the production image (backend/Dockerfile's
`production` stage — `CMD gunicorn config.wsgi:application --config
gunicorn.conf.py`). Read once at process startup.

GUNICORN_WORKERS/GUNICORN_TIMEOUT let an operator tune for the actual host
without rebuilding the image. The worker-count default is deliberately
derived from the container's own visible CPU count (gunicorn's own
conventional `(2 * cpu_count) + 1` formula) rather than a fixed number that
would be wrong on a bigger or smaller machine.

Graceful shutdown needs no extra configuration here: gunicorn's default
behavior on SIGTERM is already a graceful shutdown (stop accepting new
connections, finish in-flight requests within `graceful_timeout`, then
exit) — the ENTRYPOINT's `exec "$@"` (see entrypoint.sh) is what makes sure
gunicorn actually receives that signal directly as PID 1, instead of a
shell swallowing it.
"""

import multiprocessing
import os


def _int_env(name: str, default: int) -> int:
    # `or default` (not a plain os.environ.get default) so a variable that's
    # present but empty — e.g. GUNICORN_WORKERS= in .env, the documented
    # "leave blank to use the default" convention — falls through to
    # `default` too, not just a genuinely absent variable. This file is
    # loaded directly by gunicorn's own config-file machinery, outside
    # Django's settings pipeline, so it deliberately doesn't import
    # apps.core.env for this one-line equivalent rather than reaching into
    # a Django app module during gunicorn's own bootstrap.
    return int(os.environ.get(name) or default)


bind = "0.0.0.0:8000"
workers = _int_env("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1)
timeout = _int_env("GUNICORN_TIMEOUT", 30)

# Docker-friendly: both go to the container's own stdout/stderr, not files.
accesslog = "-"
errorlog = "-"

# Appends the request ID onto gunicorn's own default access-log line by
# reading it straight off the *response* header apps.core.middleware.
# RequestIdMiddleware always sets (%({header}o)s reads a response header;
# the header name matches REQUEST_ID_HEADER's own default — this file is
# loaded outside Django's settings, so it can't read that setting and
# instead hardcodes the same literal default value it documents).
#
# This is deliberately NOT routed through Django's LOGGING config (see
# apps.core.log_context.build_logging_config's docstring and
# docs/OBSERVABILITY.md "Known limitations"): gunicorn's access-log call
# happens after RequestIdMiddleware's own request-scoped context has
# already been cleared, so the request_id field a shared filter would add
# is unavailable there — the header atom below is the only place this
# access line can genuinely carry it.
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" rid=%({X-Request-ID}o)s'
)
