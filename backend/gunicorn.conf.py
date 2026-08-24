"""Gunicorn configuration for the production image (backend/Dockerfile's
`production` stage — `CMD gunicorn config.wsgi:application --config
gunicorn.conf.py`). Read once at process startup.

GUNICORN_WORKERS/GUNICORN_TIMEOUT let an operator tune for the actual host
without rebuilding the image. The worker-count default is deliberately
derived from the container's actual CPU quota (QUORFIX_BACKEND_CPUS,
matching docker-compose.prod.yml's `cpus:` limit — see
_default_worker_count() below) using gunicorn's own conventional
`(2 * cpu_count) + 1` formula, rather than a fixed number that would be
wrong on a bigger or smaller machine.

Graceful shutdown needs no extra configuration here: gunicorn's default
behavior on SIGTERM is already a graceful shutdown (stop accepting new
connections, finish in-flight requests within `graceful_timeout`, then
exit) — the ENTRYPOINT's `exec "$@"` (see entrypoint.sh) is what makes sure
gunicorn actually receives that signal directly as PID 1, instead of a
shell swallowing it.
"""

import math
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


def _default_worker_count() -> int:
    """gunicorn's own `(2 * cpu_count) + 1` convention, sized from the
    container's actual CPU quota rather than the host's CPU count.

    `multiprocessing.cpu_count()` reports every CPU the *host kernel* sees —
    it does not know about a `docker-compose.prod.yml`-style `cpus:` cgroup
    quota (QUORFIX_BACKEND_CPUS, default 1.0) at all. On any host with more
    CPUs than that quota — a normal shared multi-core machine running
    several capped services, not an edge case — this previously oversized
    the worker pool badly enough to OOM-crash-loop the container under
    QUORFIX_BACKEND_MEM_LIMIT's default 512m (confirmed via a clean-install
    drill: 16 host CPUs produced 33 workers, each one a full Django
    process). The backend service's `env_file: .env` already forwards
    QUORFIX_BACKEND_CPUS into the container, so it's read directly here —
    no new plumbing needed.

    QUORFIX_BACKEND_CPUS being *present but blank* — .env.example's own
    documented "leave blank for the default" convention, and so the most
    common case, not an edge case — must default to the same 1.0 that
    docker-compose.prod.yml's `cpus: ${QUORFIX_BACKEND_CPUS:-1.0}` actually
    assigns the container as its quota in that case, not fall through to
    the host CPU count: `env_file` sets the variable in the container's
    environment even when its value is empty, so `os.environ.get(...)`
    returning `""` here still means "running under this topology, quota is
    the documented default" — distinct from the variable being fully absent
    from the environment (`None`), which only happens outside
    docker-compose.prod.yml's topology, where no such quota exists to read
    and the host CPU count is the only information available.
    """
    raw = os.environ.get("QUORFIX_BACKEND_CPUS")
    if raw is None:
        return multiprocessing.cpu_count() * 2 + 1
    try:
        cpu_quota = float(raw) if raw else 1.0
    except ValueError:
        cpu_quota = 1.0
    return math.ceil(cpu_quota) * 2 + 1


bind = "0.0.0.0:8000"
workers = _int_env("GUNICORN_WORKERS", _default_worker_count())
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
