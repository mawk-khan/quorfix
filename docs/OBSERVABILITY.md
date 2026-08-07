# Observability

How Quorfix Community logs, correlates, and reports on its own operational state: log
format, request correlation IDs, what Django/Gunicorn/Celery each contribute, which events are
considered operationally important, the sensitive-data policy those logs are held to, and how
to collect and read them. No external monitoring vendor is required for any of this — everything
here writes to the container's own stdout/stderr.

## Log output format

Every backend process (`backend`, `celery_worker`) shares one `LOGGING` configuration, built by
`backend/apps/core/log_context.py`'s `build_logging_config()` and wired into each of
`config/settings/{base,development,test,production}.py`. A single "console" handler on the root
logger is the only handler anywhere in the tree — every other configured logger
(`django`, `django.request`, `django.security`, `gunicorn.error`, `celery`) is deliberately
handler-less with `propagate: True`, so a message is formatted and written exactly once
regardless of which logger emitted it.

Format is controlled by the `LOG_FORMAT` setting (env var of the same name):

| Value | Shape | Default in |
| --- | --- | --- |
| `json` | One JSON object per line (`JsonFormatter`) | production |
| `text` | Stable `key="value"` layout, not JSON (`RequestTextFormatter`) | — |
| `plain` | Human-readable `timestamp level logger [request_id] message` | development, test |

A multi-line traceback never produces multiple log lines: `JsonFormatter` embeds it as a single
string field (`exc_info`), and `RequestTextFormatter` collapses its internal newlines into `" | "`
— both formatters are safe to parse strictly one-line-per-record.

Example JSON line (production, fake IDs):

```json
{"timestamp": "2026-08-06T19:31:07.449123Z", "level": "INFO", "logger": "apps.core.request", "message": "request completed", "request_id": "46fc95d28b034a72a82d4b7f912afc3b", "task_id": "-", "environment": "production", "service": "quorfix-backend", "user_id": "-", "organization_id": "-", "http_method": "DELETE", "http_route": "/api/bugs/<uuid:bug_id>/attachments/<uuid:pk>/", "http_status": 200, "duration_ms": 42.7}
```

## Request IDs

Every HTTP request gets a correlation ID, established by
`backend/apps/core/middleware/request_id.py`'s `RequestIdMiddleware` — the first custom
middleware in `MIDDLEWARE` (immediately after `SecurityMiddleware`), so it covers essentially all
request processing and exception handling.

Behavior:

- Reads the incoming `X-Request-ID` request header (configurable via the `REQUEST_ID_HEADER`
  setting) **only when it's syntactically safe**: 1–128 characters, matching
  `^[A-Za-z0-9._-]+$`. This excludes control characters (including CR/LF) implicitly — they
  simply aren't in that character class — so a header value can never be used to inject extra
  log lines or response headers.
- Otherwise generates a new one (`uuid4().hex`).
- Never derived from the session or an authenticated user — a request ID stays available and
  stable for anonymous requests (setup, login, health checks) and is never itself a value that
  identifies who made the request.
- Stored in a `contextvars.ContextVar` for the request's lifetime (safe under threads and
  async), reset in a `finally` block so it can never leak into whatever the same worker
  thread/process handles next.

## `X-Request-ID` response header behavior

`RequestIdMiddleware` sets `X-Request-ID` (or whatever `REQUEST_ID_HEADER` is configured to) on
every response, including error responses (404s, 500s) — the ID is bound before
`get_response()` is called, so it's already active when Django's own exception handling runs.

To correlate a specific browser/API request against server-side logs: read `X-Request-ID` from
the response (e.g. browser DevTools' Network tab, or `curl -i`), then grep the backend log for
that value.

## Django, Gunicorn, and Celery correlation

- **Django** (`django`, `django.request`, `django.security`): routed through the shared root
  handler (see above) — every Django-internal log line (including a 500's traceback, via
  `django.request`) carries `request_id` through the same `RequestContextFilter` every
  application logger uses.
- **Gunicorn error log** (`gunicorn.error`): also routed through the shared handler for
  consistent formatting of gunicorn's own startup/worker-lifecycle messages. Messages emitted
  before Django's settings load (gunicorn's very first "Starting gunicorn..." lines) predate
  this configuration and use gunicorn's own default format instead — a minor, cosmetic gap.
- **Gunicorn access log** (`gunicorn.access`): **deliberately NOT routed through Django's
  `LOGGING`.** Gunicorn's access-log call includes every request/response header as raw "safe
  atoms" (`extra={...}`); reconfiguring that logger to use `JsonFormatter` would blindly dump
  every one of those atoms (potentially including headers this project has no reason to vet,
  like `Referer` or `Cookie`) into structured log output — a real risk the JSON formatter's own
  denylist is only a defense-in-depth backstop against, not a primary control for. Instead,
  `backend/gunicorn.conf.py` sets `access_log_format` directly, appending
  `rid=%({X-Request-ID}o)s` — reading the request ID straight off the **response header**
  `RequestIdMiddleware` already sets, with no dependency on Django's logging config at all. This
  is a genuine, working correlation mechanism, not a placeholder: grep a gunicorn access line for
  `rid=<the request ID>` to find the exact access-log entry for a given request. See
  [Known limitations](#known-limitations) for the one nuance this doesn't cover.
- **Celery** (`celery`, and every `apps.*` task logger): also routed through the shared root
  handler. `CELERY_WORKER_HIJACK_ROOT_LOGGER = False` (`config/settings/base.py`) is required
  for this to work at all — without it, Celery's own worker bootstep reconfigures the root
  logger with its own formatting *after* Django's `LOGGING` has already set it up, silently
  discarding every field this document describes for every task log line.

Task-level correlation (propagating a request's ID into the Celery tasks it dispatches) is
covered next.

## Celery task correlation

`backend/apps/core/task_correlation.py` provides two pieces:

- `correlation_headers()` — called at every dispatch site
  (`apps.notifications.services.notify`, `apps.notifications.tasks.create_notifications_for_event`'s
  own dispatch of `send_notification_email`, `apps.attachments.services.remove_attachment`).
  Returns `{"quorfix_correlation_id": get_request_id()}` when a request is in progress, or `{}`
  otherwise — dispatched via Celery's `apply_async(headers=...)`, never as a mandatory
  positional/keyword task argument, so no task's call signature changed and no dedup key
  (`apps.notifications.tasks`' `(organization, recipient, dedup_key)` uniqueness) was touched.
  The header key is deliberately namespaced rather than the more obvious `"correlation_id"` —
  that name collides with an unrelated, pre-existing `correlation_id` attribute Celery's own
  worker-side `Context` class already defines (AMQP's own correlation-id property, populated
  with the task's message id), which silently strips a same-named custom header from a task
  actually received over a real broker (confirmed by a live end-to-end test — Celery's `.apply()`
  eager/local path used by every unit test never exhibits this, only a real dispatch does; see
  `backend/apps/core/tests/test_task_correlation.py`'s
  `TestHeaderKeyDoesNotCollideWithCeleryInternals` for the regression guard).
- `task_correlation_context(self)` — a context manager every correlation-aware task body wraps
  itself in. Uses the propagated header when present; otherwise generates a fresh task-local ID,
  so a task triggered by a non-HTTP source (a retry, another task, Celery beat) still logs under
  a stable ID of its own instead of falling back to `"-"` for its entire execution. The bound ID
  is cleared when the `with` block exits, the same way `RequestIdMiddleware` clears its own.

Every log line emitted from inside such a task also carries `task_id` (the Celery task's own
UUID, read from `celery.current_task` by the shared `RequestContextFilter` — automatic, no
per-call-site code needed).

Tasks with correlation wired in: `create_notifications_for_event`, `send_notification_email`,
`delete_attachment_object`.

## Important operational events

| Event | Where | Level |
| --- | --- | --- |
| Notification task dispatch (broker) failure | `apps.notifications.services.notify` | ERROR (`.exception`) |
| Notification email dispatch failure | `apps.notifications.tasks.create_notifications_for_event` | ERROR (`.exception`) |
| Notification email send failure (retrying) | `apps.notifications.tasks.send_notification_email` | WARNING |
| Notification email permanently failed (retries exhausted) | `apps.notifications.tasks._mark_email_failed` | ERROR |
| Notification email UPDATE affected zero rows (concurrent send) | `apps.notifications.tasks.send_notification_email` | WARNING |
| Attachment cleanup dispatch (broker) failure | `apps.attachments.services.remove_attachment` | ERROR (`.exception`) |
| Attachment cleanup failure (retrying) | `apps.attachments.tasks.delete_attachment_object` | WARNING |
| Attachment cleanup permanently failed (retries exhausted) | `apps.attachments.tasks.delete_attachment_object` | ERROR |
| Attachment marked uploaded but storage object missing | `apps.attachments.services.get_download_path` | ERROR |
| Analytics cache read/write failure (falls back to direct query) | `apps.analytics.caching.cache_or_compute` | WARNING |
| Readiness: database/cache/attachment-storage unavailable | `apps.core.views.ReadinessCheckView` | ERROR |
| Login success / failure | `apps.accounts.views.LoginView` | INFO / WARNING |
| Logout | `apps.accounts.views.LogoutView` | INFO |
| Instance setup completed / rejected | `apps.organizations.views.SetupView` | INFO / WARNING |
| Invitation accepted / rejected | `apps.organizations.views.InvitationAcceptView` | INFO / WARNING |
| Production configuration validation failure | `apps.core.checks` (`quorfix.E0xx`, via `manage.py check`, run by `backend/entrypoint.sh` before the real process starts) | Django system-check `Error` |

Deliberately **not** logged at INFO or above: successful health/readiness probes (an
orchestrator may call these every few seconds — see
[Health and readiness](#health-and-readiness)), routine notification polling, and analytics
cache hits.

## Log levels

Set via the `LOG_LEVEL` setting/env var (`DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` —
anything else fails fast with `ImproperlyConfigured`, in every environment, at settings-load
time — see `apps.core.env.get_log_level`).

| Environment | Default `LOG_LEVEL` | Default `LOG_FORMAT` |
| --- | --- | --- |
| production | `INFO` | `json` |
| development | `DEBUG` | `plain` |
| test | `WARNING` | `plain` |

Test's default is intentionally quiet — `pytest`'s own `caplog` fixture captures `LogRecord`s
directly regardless of the root logger's level or formatter, so individual tests that need to
assert on INFO/DEBUG-level messages use `caplog.at_level(...)` themselves rather than relying on
this default; it only controls what a human sees in pytest's own captured-log output on failure.

## Sensitive-data policy

Never logged, anywhere in this codebase — enforced by
`backend/apps/core/tests/test_logging_security.py`, including a static source scan
(`TestNoForbiddenIdentifiersInLoggerCallSites`) that fails if any future `logger.*(...)` call
site references a forbidden identifier, not just manual review:

- `DJANGO_SECRET_KEY`, database/Redis/SMTP passwords or credentialed URLs
- Login password (success or failure — failed login logs a fixed neutral message plus the
  request ID, never the submitted email or password; see
  [Known limitations](#known-limitations) for the one enumeration-adjacent nuance)
- Session cookie, CSRF token
- Raw invitation token (only its SHA-256 hash — `Invitation.token_hash` — is ever persisted or
  would be loggable; the raw token itself is never passed to a logger call)
- Attachment body, original filename, or absolute filesystem path — attachment failures log
  `attachment.id` and a non-reversible hash of the storage key
  (`apps.attachments.providers.hash_storage_key`) instead of the raw key (which otherwise embeds
  the organization/bug/attachment UUID structure) or any path
- Comment body, notification email body or recipient address

`RequestContextFilter` (`apps/core/log_context.py`) also carries a small denylist
(`password`, `email`, `session`, `cookie`, `csrf_token`, `token`, `secret`, `authorization`) that
strips any matching key from a logger call's `extra=` kwargs before formatting — defense in
depth, not the primary control, since no call site in this codebase passes those today.

The logging filter itself never queries the database or reads the session — it only reads
already-resolved values out of `contextvars` (`apps.core.context`,
`apps.core.middleware.request_id`).

## Container log collection

Every process writes to stdout/stderr only — never a container-local file:

- `backend` / `celery_worker`: Django's `LOGGING` (above).
- Gunicorn (`backend/gunicorn.conf.py`): `accesslog = "-"`, `errorlog = "-"`.

This means standard container log collection (`docker compose logs`, `docker logs`, or
whatever log driver/shipper an operator's platform provides — Docker's `json-file`, `journald`,
a cloud provider's log agent, etc.) captures everything with no extra configuration. Nothing in
this project writes to a file under the container filesystem that would need a separate volume
or rotation policy.

```sh
# Follow backend logs
docker compose logs -f backend

# Follow worker logs
docker compose logs -f celery_worker

# Production stack
docker compose -f docker-compose.prod.yml logs -f backend celery_worker
```

## Health and readiness

- `GET /api/health/` (liveness) — never touches the database, cache, or attachment storage; a
  process that can answer this at all is alive. Never logs anything for a successful call.
- `GET /api/health/ready/` (readiness) — checks database, cache, and attachment storage; returns
  `503` if any is unhealthy. Failure detail (exception text, storage check detail) goes to the
  server log only — the response body is always a fixed component name plus an `ok`/not-`ok`
  flag, never exception text or a connection string.
- Neither endpoint logs a successful probe at INFO or above — see
  `TestSuccessfulProbesDoNotFloodLogs` in `backend/apps/core/tests/test_health_and_readiness.py`.
  The optional request-completion log (below) specifically logs these two paths at DEBUG instead
  of INFO for the same reason.
- Startup: `backend/entrypoint.sh` runs `manage.py check` (every `quorfix.E0xx` production
  check — see `apps/core/checks.py`) and `manage.py check_attachment_storage` before the real
  process (`gunicorn`/`celery`) starts, so a misconfigured production container fails loudly at
  startup instead of only at first request. Both write through Django's normal
  management-command output (`self.stdout`/`CommandError`), not the logging framework — plain,
  secret-free text either way.

## Request timing (optional)

`backend/apps/core/middleware/request_logging.py`'s `RequestLoggingMiddleware` (placed
immediately after `RequestIdMiddleware`) logs one `"request completed"` line per request with
`http_method`, `http_route` (the resolved URL pattern, e.g.
`/api/bugs/<uuid:bug_id>/attachments/<uuid:pk>/` — never the raw path with real IDs interpolated,
and never the query string or request body), `http_status`, and `duration_ms` (measured with
`time.monotonic()`). Logged at DEBUG for the two health/readiness paths, INFO otherwise.

## Monitoring integration points

No external monitoring vendor is required or assumed. If you run one:

- **Log-based**: point a log shipper (Fluent Bit, Vector, a cloud provider's agent, etc.) at
  stdout/stderr as collected above; with `LOG_FORMAT=json` in production, every field described
  in this document is already structured and queryable without a custom parser.
- **Correlation**: `request_id` is the join key across a request's application logs, its
  gunicorn access-log line (`rid=` atom), and any Celery task logs it triggered
  (`quorfix_correlation_id` header, echoed as that task's own `request_id`/`task_id` fields).
- **Uptime/synthetic checks**: `GET /api/health/` (liveness) and `GET /api/health/ready/`
  (readiness) are the two endpoints to point an external checker at; see
  [Health and readiness](#health-and-readiness).
- **Metrics**: none are emitted (no Prometheus endpoint, no StatsD/OpenTelemetry integration) —
  out of scope for this chunk; the `duration_ms` field on the request-completion log is the
  closest built-in substitute today, extractable by any log-based metrics pipeline.

## Known limitations

Documented honestly rather than left implicit:

- **Gunicorn access-log correlation lives in the message text, not a structured field.** The
  `rid=` atom is embedded inside `gunicorn.access`'s single pre-rendered message string (gunicorn
  renders the whole access-log line itself before it ever reaches Python's logging layer), not
  as a top-level `request_id` JSON field the way every other logger's lines carry it. Grep or a
  regex-capable log query still finds it (`rid=<value>`); a query designed only around the
  top-level `request_id` field will miss access-log lines.
- **Gunicorn's very first startup lines predate Django's logging config** (see
  [Django, Gunicorn, and Celery correlation](#django-gunicorn-and-celery-correlation)) — cosmetic
  only, doesn't affect anything logged once the process is actually serving traffic.
- **No metrics/tracing integration** — see [Monitoring integration points](#monitoring-integration-points).
- **User/organization ID are only ever included when already resolved by
  `OrganizationAwareSessionAuthentication`** (i.e., an authenticated, session-based DRF request)
  or explicitly bound by a view that authenticates outside DRF's pipeline (`LoginView`,
  `SetupView`, `InvitationAcceptView`). An anonymous request, or one authenticated through a
  future mechanism that doesn't call `apps.core.context.bind_actor_context`, logs `user_id`/
  `organization_id` as `"-"` even once a user is technically known later in the request.
- **Failed-login logging is neutral by design, not silent** — every failed attempt logs a fixed
  `"Login failed"` message (see [Sensitive-data policy](#sensitive-data-policy)) rather than
  varying by outcome, specifically so the log itself can't become an account-enumeration side
  channel alongside the identical response `EmailAuthBackend`'s existing timing defense already
  guarantees (`backend/apps/accounts/backends.py`). This means a failed-login log line alone
  cannot tell you *why* it failed (wrong password vs. unknown email) — that's the intended
  trade-off, not a gap to close later.

## Troubleshooting examples

**"A user reports an error — find everything the server logged for their request."**

1. Get the request ID from the browser (DevTools → Network → the failing request → Response
   Headers → `X-Request-ID`) or from the API response if the client surfaces it.
2. `docker compose logs backend | grep '<request-id>'` — every application/Django log line for
   that request, plus (if `LOG_FORMAT=json`) any Celery task it dispatched, since that task's own
   `request_id` field is the same propagated correlation ID.
3. `docker compose logs backend | grep 'rid=<request-id>'` — the matching gunicorn access-log
   line (method, path, status, response size).

**"A notification email didn't arrive — was it even attempted?"**

```sh
docker compose logs celery_worker | grep '<notification-id>'
```
Notification-related log lines always include the notification ID (never the recipient address
or email body) — this finds the dispatch attempt, any retry warnings, and either the success or
the permanent-failure line.

**"Is the readiness probe actually catching a real Redis outage?"**

```sh
docker compose stop redis
curl -i http://localhost:8000/api/health/ready/   # expect 503, components.cache.ok: false
docker compose logs backend | tail -5             # expect an ERROR line: "Readiness check: cache is unavailable"
docker compose start redis
```

**"Confirm no secrets appear even under a simulated failure."**

```sh
docker compose logs backend | grep -iE 'password|secret|token' 
```
Expect zero matches against real credential values (log lines using the literal words "password"
or "token" as part of a safe, fixed message — e.g. none currently exist in this codebase's actual
log lines — would be the only kind of hit; see
`backend/apps/core/tests/test_logging_security.py` for the automated version of this check).
