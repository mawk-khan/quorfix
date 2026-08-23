# Demo / Community-Beta Deployment

This document covers what's specific to running Quorfix as a public, invite-only
demo/community-beta instance (e.g. at `demo.quorfix.com`) — isolation from any real/production
deployment, the account model, account recovery, and the data reset procedure. It assumes you've
already read [`docs/INSTALLATION.md`](./INSTALLATION.md), [`docs/SECURITY.md`](./SECURITY.md),
and [`docs/BACKUP_AND_RESTORE.md`](./BACKUP_AND_RESTORE.md) — this doc doesn't repeat their
content, only what changes for a demo instance.

## 1. Isolation boundary

The demo **must** be a fully separate deployment from any real/customer/production instance —
never the same `docker-compose.prod.yml` project sharing infrastructure with anything else.
Concretely, the demo needs its own:

- **Database** — its own PostgreSQL instance/volume (`postgres_data`), never a schema or
  database shared with a real installation.
- **Secret key** — its own `DJANGO_SECRET_KEY`, generated independently (never copy a real
  deployment's value into the demo's `.env`, or vice versa).
- **Administrator credentials** — its own value for `DEMO_ADMIN_PASSWORD` (see §2), unrelated to
  any real installation's admin password.
- **Application environment** — its own `.env` file, its own `POSTGRES_PASSWORD`, its own
  `REDIS_URL`/Redis instance. Nothing here is ever copied from or shared with a real deployment.
- **Uploads/storage** — its own `attachments_data` volume. Never point the demo's
  `ATTACHMENTS_LOCAL_ROOT` at a real installation's attachment volume.
- **No customer data** — never restore a real installation's backup into the demo, and never
  restore the demo's backup into a real installation (see §4's golden-snapshot naming
  convention, which exists specifically to make the two hard to confuse).
- **No production licensing secrets, no production API credentials** — the demo has no license
  keys or Professional entitlements to leak in the first place today (see `CLAUDE.md`'s
  Community/Professional boundary — Professional, including licensing, isn't built yet), but
  this remains true going forward: never configure the demo with real licensing/API credentials
  belonging to an actual commercial deployment.

The practical way to make this hard to get wrong by accident: give the demo its own directory
checkout (or its own `--env-file`/`--project-name`), its own `.env` with a name that makes it
obvious (e.g. `.env.demo`, never just `.env` reused from a real deployment's copy), and never run
`make` targets against the demo and a real deployment from the same shell session without
double-checking `ENV_FILE=`/`COMPOSE_FILE=` first.

## 2. Account model

**`INITIAL_DEMO_ACCOUNT_MODEL=invite-only`**

Quorfix Community has no self-service registration today (see `apps/accounts/urls.py` —
only `login`/`logout`; account creation is exclusively the one-time `/api/setup/` flow plus
admin-issued invitations, see `apps/organizations/views.py`). This is preserved as-is for the
demo — no self-registration was added or is planned for this deployment. Concretely, this means:

- The demo's single organization and its administrator account are created once via `/setup`
  (or `seed_demo` — see §4) when the instance is first stood up.
- Every other demo account either comes from `seed_demo`'s five fixed personas (documented in
  [`docs/ACCESS_AND_TESTING.md`](./ACCESS_AND_TESTING.md)) or from an admin-issued invitation.
- An anonymous visitor cannot create their own account. If the demo is meant to let arbitrary
  visitors explore the product hands-on, the intended path is signing in with one of those five
  fixed personas — not registering their own.

**Quick Access (`QUORFIX_DEMO_MODE=true`)** is the actual mechanism visitors use for that path on
a public instance like this one — see
[`docs/ACCESS_AND_TESTING.md`](./ACCESS_AND_TESTING.md#demo-quick-access-role-login) for the full
description. It authenticates a visitor as one of the five personas above by role, never by
password (the visitor never sees, needs, or can extract any password — including the
`DEMO_ADMIN_PASSWORD` this document already treats as sensitive, see §1). It's a separate flag
from `QUORFIX_DISPOSABLE_DATABASE` above: enabling it doesn't seed or reset any data by itself,
and it must be set in this deployment's own `.env` (never copied from, or shared with, a real
installation's `.env` — same rule as every other value in §1). Defaults to `false`; a real
customer/production deployment has no reason to ever set it.

Building real self-registration is future Professional/Community work, out of scope for this
deployment.

## 3. Account recovery

- **Normal demo users** (the five `seed_demo` personas): recovered by re-running `seed_demo`
  (§4) — it reconverges each persona's password back to its documented value on every run.
- **A real invited teammate who forgot their password**: there is no self-service password
  reset (`docs/SECURITY.md` and the pre-deployment review both note this honestly — it's a
  genuine Community gap, not demo-specific). The current recovery procedure requires shell
  access to the backend container:

  ```bash
  docker compose -f docker-compose.prod.yml exec backend python manage.py shell -c "
  from apps.accounts.models import User
  u = User.objects.get(email='someone@example.com')
  u.set_password('a-new-temporary-password')
  u.save(update_fields=['password'])
  "
  ```

  Note `manage.py changepassword <username>` is **not** usable here even though it looks like
  the obvious tool: `AUTH_USER_MODEL`'s `USERNAME_FIELD` is still the inherited `username`
  field, which every account-creation path (`setup_instance`/`accept_invitation`, see
  `apps/organizations/services.py`) sets to an opaque random UUID hex, never the user's email —
  an operator has no practical way to know it. The shell snippet above, looking the user up by
  email instead, is the real current procedure.
- **What would need to change before open public registration**: a real password-reset flow
  (token generation/expiry, an email-delivery path, a frontend form) — this is real,
  unimplemented work, not merely undocumented. It is **not** a blocker for this invite-only
  first deployment; every account on it is either a fixed demo persona or admin-recoverable via
  the shell snippet above.

## 4. Demo data reset (heavy: full snapshot restore)

**For routine/scheduled resets, use `scripts/demo reset-demo` instead — see §7.** This section's
golden-snapshot restore procedure is the *heavier* alternative: a full database/attachments
replacement from a point-in-time backup, useful as a disaster-recovery fallback (e.g. if the
demo's data somehow reaches a state `scripts/demo reset-demo`'s application-aware reset can't
cleanly recover from) or when the canonical seed dataset itself changes and needs recapturing.
It reuses the same hardened backup/restore path documented in `docs/BACKUP_AND_RESTORE.md`
rather than new, independently-risky code — `seed_demo` is idempotent (see
`backend/apps/core/tests/test_seed_demo.py`), and `scripts/restore_db.sh`/
`scripts/restore_attachments.sh` are already exactly "stop writes → replace the database
wholesale → migrate → restart", already tested
(`scripts/tests/test_backup_restore_guards.sh`), and already require an explicit
`--confirm-restore` flag plus a checksum-verified dump.

### One-time: capture a golden snapshot

After seeding the demo for the first time (and any time the canonical demo dataset
intentionally changes — a new Quorfix release with different seed data, for example), capture a
recovery set to reset back to:

```bash
# 1. Seed the demo (see docs/ACCESS_AND_TESTING.md for the full command and
#    what QUORFIX_DISPOSABLE_DATABASE / DEMO_ADMIN_PASSWORD mean).
QUORFIX_DISPOSABLE_DATABASE=true DEMO_ADMIN_PASSWORD='<demo-specific admin password>' \
  docker compose -f docker-compose.prod.yml exec backend python manage.py seed_demo

# 2. Capture a coordinated database + attachments recovery set. DEST must
#    be outside the repository and outside any web-served path.
make backup DEST=/srv/quorfix-demo-golden COMPOSE_FILE=docker-compose.prod.yml
```

`make backup` writes a timestamped `quorfix-backup-<UTC-timestamp>/` directory containing
`database.dump`, `attachments.tar.gz`, `checksums.sha256`, and `manifest.txt` — keep the whole
directory together (see `docs/BACKUP_AND_RESTORE.md` §2, "Recovery-set concept"). Name the
parent directory something unambiguous, e.g. `quorfix-demo-golden`, distinct from any real
deployment's own backup naming — this is what makes it hard to accidentally restore the demo's
golden snapshot into a real installation, or vice versa (see §1).

### Repeatable: reset to the golden snapshot

```bash
make restore-db-confirm IN=/srv/quorfix-demo-golden/quorfix-backup-<ts>/database.dump \
  COMPOSE_FILE=docker-compose.prod.yml
make restore-attachments-confirm IN=/srv/quorfix-demo-golden/quorfix-backup-<ts>/attachments.tar.gz \
  COMPOSE_FILE=docker-compose.prod.yml
```

Each command already performs the full documented procedure end to end (see
`scripts/restore_db.sh`'s and `scripts/restore_attachments.sh`'s own header comments and
`docs/BACKUP_AND_RESTORE.md` §8 for the exact steps): stop `backend`/`celery_worker`, verify the
dump's checksum, drop and recreate the database (or replace the attachments volume), restore the
snapshot, run migrations forward, and restart services. `frontend` is never stopped — it has no
direct database/attachment access of its own, so a brief backend/worker outage during reset is
the only visible interruption, and typically finishes in well under a minute for a dataset this
size.

**This snapshot-restore procedure remains manual-only, deliberately** — it is the heavy,
whole-database fallback, not the routine reset (see §7 for the scheduled/automatic mechanism).
An operator triggers it manually using the two commands above only when §7's lighter reset isn't
the right tool (see this section's opening paragraph).

### Safety notes

- Both restore commands refuse to run without `--confirm-restore` (enforced by `make
  restore-*-confirm`'s own `IN=` requirement plus the underlying script) and refuse a dump
  whose checksum doesn't match — an incomplete or corrupted golden snapshot cannot be restored
  by accident.
- Restoring **replaces the entire target database**. This is exactly why §1's isolation
  boundary matters: the golden-snapshot restore commands above must only ever be pointed at the
  demo's own `docker-compose.prod.yml`/`.env` (via `COMPOSE_FILE=`/`ENV_FILE=` if the demo
  doesn't use the default filenames) — never at a real deployment's.
- If the demo's seed dataset or schema changes (a new release), recapture the golden snapshot
  (§4, "One-time") before the next reset — restoring an old snapshot after a schema change would
  restore data, then the restore script's own forward-migration step brings the schema current,
  so this is safe, but the *content* reverts to whatever the snapshot captured, not the new
  release's seed data, until it's recaptured.

## 5. Operator commands (scripts/demo)

A single operator entry point, `scripts/demo`, wraps the Docker Compose commands, health
endpoints, and backup script referenced throughout this document into one predictable interface
— so day-to-day demo operation doesn't require remembering the exact `docker compose` invocation
each time. It targets `docker-compose.prod.yml` and reuses the exact same `apps.core.checks`
production hardening, health endpoints (`/api/health/`, `/api/health/ready/`), and
`scripts/backup.sh`/`scripts/upgrade_smoke.sh` already documented elsewhere in this repo — it
introduces no new deployment mechanism.

### Prerequisites

- Docker with the `docker compose` v2 plugin.
- A `.env.demo` file at the repository root (copy `.env.example` and fill it in — see §1's
  isolation checklist for what must be unique to the demo). It **must** contain the line
  `QUORFIX_ENV=demo`, verbatim — every `scripts/demo` command refuses to run otherwise. This is
  an ops-only safety marker read by the script itself, unrelated to any application-level flag
  (e.g. `QUORFIX_DEMO_MODE`, which gates the Quick Access feature — see
  `docs/ACCESS_AND_TESTING.md`).
- `docker-compose.prod.yml` is the default Compose file; override either default with the
  `COMPOSE_FILE`/`ENV_FILE` environment variables if this deployment doesn't use the standard
  filenames (e.g. `ENV_FILE=/etc/quorfix-demo/.env.demo scripts/demo status`).

Every command prints which Compose file and env file it resolved to before doing anything.

### Commands

```bash
scripts/demo deploy    # build images, apply migrations, restart, verify health
scripts/demo start     # start services (no migrations)
scripts/demo stop      # stop services — volumes and data are never touched
scripts/demo restart   # restart services (no migrations, no data loss)
scripts/demo status    # show service state (docker compose ps)
scripts/demo health    # liveness/readiness/frontend/migration checks — prints PASS or FAIL
scripts/demo logs [SERVICE]   # follow logs; SERVICE is one of db, redis, backend, celery_worker, frontend
scripts/demo backup [DIR]     # coordinated database + attachments backup (default: ~/quorfix-demo-backups)
scripts/demo reset-demo --confirm   # guarded reset to canonical demo state — see §7
scripts/demo help
```

Typical workflow before and after routine maintenance:

```bash
scripts/demo backup
scripts/demo deploy
scripts/demo health
```

`scripts/demo deploy` never runs `git pull`, switches branches, or touches Git in any way — the
administrator or CI prepares the source checkout first, so a deploy is deterministic and
reproducible from whatever commit is already checked out. It also never seeds or resets demo
data; run `seed_demo` separately (§2 above), same as always.

### Operational safety notes

- `stop` runs `docker compose stop`, never `docker compose down -v` or anything that removes
  containers, images, or volumes — `postgres_data`, `redis_data`, and `attachments_data` are
  never touched by any `scripts/demo` command.
- `logs` only ever accepts one of the five service names Compose actually defines; anything else
  is rejected before it ever reaches a `docker compose` invocation.
- `backup` requires an absolute destination path and refuses to write inside the repository
  (enforced by `scripts/backup.sh` itself) — see §4's "Demo data reset" for the full recovery-set
  format it produces.
- No command loads or evaluates `.env.demo` as shell — it's only ever read by
  `docker compose --env-file` and grepped for the one `QUORFIX_ENV=demo` line.

## 6. Security hardening for this deployment

Full rationale for everything below lives in [`docs/SECURITY.md`](./SECURITY.md) — this section
is only the concrete checklist for standing up `.env.demo` and the edge in front of it. Nothing
here is a substitute for reading that document.

### Required in `.env.demo`

In addition to `QUORFIX_DEMO_MODE=true` and `QUORFIX_ENV=demo` (§5):

```bash
QUORFIX_DEMO_MAIL_SINK=<a mailbox an operator actually reads>
```

Required — `manage.py check` fails (`quorfix.E013`) at container startup without it. Every
demo-triggered email (invitation attempts, notification email) is redirected here instead of its
real recipient; see `docs/SECURITY.md` "Mail sink (public demo)".

### Optional overrides

Sane defaults apply if left unset — only set these if this host's actual resources or risk
tolerance genuinely need something different (see `docs/SECURITY.md` "Container resource
limits", "Session lifetime (public demo)", "Upload policy (public demo)"):

```bash
QUORFIX_DEMO_SESSION_COOKIE_AGE_SECONDS=   # default 4 hours
QUORFIX_DEMO_MAX_ATTACHMENT_SIZE_BYTES=    # default 2 MB
QUORFIX_DB_MEM_LIMIT= QUORFIX_DB_CPUS= QUORFIX_DB_PIDS_LIMIT=
QUORFIX_REDIS_MEM_LIMIT= QUORFIX_REDIS_CPUS= QUORFIX_REDIS_PIDS_LIMIT=
QUORFIX_BACKEND_MEM_LIMIT= QUORFIX_BACKEND_CPUS= QUORFIX_BACKEND_PIDS_LIMIT=
QUORFIX_CELERY_MEM_LIMIT= QUORFIX_CELERY_CPUS= QUORFIX_CELERY_PIDS_LIMIT=
QUORFIX_FRONTEND_MEM_LIMIT= QUORFIX_FRONTEND_CPUS= QUORFIX_FRONTEND_PIDS_LIMIT=
QUORFIX_LOG_MAX_SIZE= QUORFIX_LOG_MAX_FILES=
```

### What's already enforced by the application/Compose file (no operator action needed)

- The five Quick Access personas' role/membership can never be changed or removed via the API,
  and no sixth member can be invited into the demo organization — see `docs/SECURITY.md`
  "Immutable demo personas".
- `db`/`redis`/`backend`/`celery_worker` publish no host port; only `frontend` does.
- Every service has a bounded memory/CPU/PID ceiling and bounded log rotation.

### Requires operator action — Cloudflare / edge WAF

**Not configured by anything in this repository, and cannot be** — see `docs/SECURITY.md` "Edge
/ Cloudflare WAF (public demo)" for the exact managed-WAF, bot-protection, per-path rate-limit,
and origin-protection requirements for whoever owns `demo.quorfix.com`'s Cloudflare zone. Treat
that section as a checklist to complete before `demo.quorfix.com` goes live, not as already done
because this file exists. **This remains outstanding regardless of how thoroughly §7's reset
mechanism below is exercised or scheduled — application/data hardening and edge/network
hardening are separate, both-required layers.**

## 7. Guarded automatic demo reset

`scripts/demo reset-demo --confirm` restores the public demo to its canonical state: the five
Quick Access personas, the `Quorfix Demo` organization, the three canonical projects, and the 24
canonical seed bugs — while removing every visitor-created bug, comment, attachment, project,
tag, invitation, and non-canonical membership. See `backend/apps/core/management/commands/
reset_public_demo.py`'s own module docstring for the exact, authoritative step-by-step list; this
section is the operator-facing summary and the parts of the design that live outside that file
(scheduling, backup policy, session/cache/Celery behavior).

### Manual reset

```bash
scripts/demo reset-demo --confirm
```

`--confirm` is an operational guard against a stray keystroke, not authentication — the real
safety conditions below are enforced by the backend command itself and hold regardless of this
flag. Exits non-zero and prints `DEMO RESET FAIL` on any failure (a guard refusal, a lock
conflict, a mid-reset error, or a post-reset health check failure); prints `DEMO RESET PASS` and
exits 0 only once the canonical state has been verified and the application is confirmed
healthy afterward (`scripts/demo health`, i.e. `scripts/upgrade_smoke.sh`).

### Scheduled reset

No specific host/scheduler is assumed. `scripts/demo reset-demo --confirm` is non-interactive and
safe to call repeatedly (idempotent canonical state, and the reset lock below prevents overlap),
so any of the following work — pick whichever this deployment already uses for other periodic
jobs:

**Host cron** (adjust `<deployment-path>` to wherever this checkout actually lives on the host;
never hardcode a path this repository can't know):

```cron
0 */6 * * * cd <deployment-path> && ./scripts/demo reset-demo --confirm >> /var/log/quorfix-demo-reset.log 2>&1
```

**systemd timer** (`/etc/systemd/system/quorfix-demo-reset.service`):

```ini
[Unit]
Description=Quorfix public demo reset

[Service]
Type=oneshot
WorkingDirectory=<deployment-path>
ExecStart=<deployment-path>/scripts/demo reset-demo --confirm
```

`/etc/systemd/system/quorfix-demo-reset.timer`:

```ini
[Unit]
Description=Run the Quorfix public demo reset every 6 hours

[Timer]
OnCalendar=*-*-* 00,06,12,18:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable with `systemctl enable --now quorfix-demo-reset.timer`.

**Recommended initial cadence: every 6 hours.** Not hardcoded anywhere in the reset command
itself — purely an external scheduling choice, changed by editing the cron line or the systemd
timer's `OnCalendar=`, with no code or redeploy involved. Don't schedule more frequently than
necessary: each run briefly returns 503 on mutating API requests (see "Concurrent mutations
during reset" below), so a tighter cadence trades demo continuity for freshness with no
correctness benefit past what visitors can actually generate in the interval.

### Safety guards (all independently enforced, backend-side)

1. `--confirm-demo-reset` was passed to the management command (the shell wrapper's `--confirm`
   maps to this — it does not itself bypass anything below).
2. `QUORFIX_DEMO_MODE=true`.
3. `QUORFIX_DEMO_RESET_ENABLED=true` — a **second, independent** flag from `QUORFIX_DEMO_MODE`;
   enabling Quick Access login alone never also enables reset. Must be set explicitly in this
   deployment's `.env`/`.env.demo` (see `.env.example`).
4. An organization slugged `quorfix-demo` must actually exist — otherwise this database doesn't
   look like a demo database at all, regardless of what the flags above claim.
5. `QUORFIX_DISPOSABLE_DATABASE=true`, transitively, via the same guard every other
   demo-seeding command already uses (`seed_demo`, called internally as the reseed step).
6. A PostgreSQL advisory lock (`apps.core.pg_advisory_lock`) — a second reset attempt while one
   is already running refuses immediately (`ERROR: demo reset already in progress`, non-zero
   exit) rather than queuing behind it. Session-scoped, so a crashed reset process's lock is
   released automatically by PostgreSQL when its connection drops — never a stuck lock file.
7. Every deletion is scoped by an explicit `organization=<the demo organization>` filter — never
   a blanket table truncation, `docker compose down -v`, `DROP DATABASE`, or `manage.py flush`.
   Non-demo users, staff/superuser accounts, and every other organization's data are structurally
   unreachable by this command regardless of what's in the demo organization.
8. The entire reset (delete transient data → repair/reseed canonical data → verify) runs inside
   one database transaction — a failure at any point rolls back everything, so a reset never
   commits a half-seeded demo. Verification (all five personas correct, canonical org/projects/
   bugs present) happens *before* commit, not after — a verification failure is a rollback, never
   a false "PASS".

### Concurrent mutations during reset

For the brief window the reset transaction is open, every organization-scoped mutating API
request (`POST`/`PUT`/`PATCH`/`DELETE`) returns `503` (`apps.core.demo_reset_guard`) — closing the
"a visitor's write lands between delete and reseed" race without per-task reset-awareness
scattered through every service module. Read requests are never blocked. Entirely inert (no
effect on request handling at all) unless `QUORFIX_DEMO_MODE=true`. A real reset typically
finishes in a few seconds against the seed dataset's actual size; the flag also carries a 15-minute
safety-net expiry so a crashed reset process can never leave the demo read-only indefinitely.

### Demo sessions and reset

```text
Demo sessions survive reset: YES
```

The five personas' `User` rows are never deleted and recreated by a reset — only repaired in
place (role, `first_name`/`last_name`, password if drifted, and `is_active`/`is_staff`/
`is_superuser` if tampered). Since the same database primary key persists, an already-authenticated
visitor's session cookie remains valid straight through a reset. This is safe specifically because
no request handler in this codebase caches organization/role from the session — `apps.
organizations.authentication.OrganizationAwareSessionAuthentication` re-reads the caller's
`OrganizationMembership` from the database on every single request — so if a reset repairs a
role that had drifted, that correction takes effect on the visitor's very next request with no
stale-permission window and no explicit session invalidation required.

### Uploaded files / media

Every attachment scoped to the demo organization is removed as part of a reset (Community's
demo upload policy keeps uploads enabled — see `docs/SECURITY.md` "Upload policy (public demo)"
— so visitor uploads do accumulate between resets and must be cleared). Each attachment's
underlying storage file is deleted via `apps.attachments.providers.get_storage_provider()` (the
same abstraction the application itself uses, never a shell `rm` against a client-derived path) —
a missing file is logged and skipped, not a fatal error for the whole reset.

### Celery during reset

No task in this codebase accepts a client-chosen task name or otherwise executes arbitrary work —
every dispatch is a fixed, known task (`apps.notifications.tasks`, `apps.attachments.tasks`).
Both already tolerate operating on a since-deleted target without corrupting anything: attachment
cleanup is idempotent (deleting an already-absent storage key is a no-op), and the maintenance
window above closes off *new* mutations (so no *new* notification/cleanup task gets queued as a
side effect of a reset) — the only remaining exposure is a task that was queued in the instant
before the window opened, which is bounded, self-tolerant, and not worth revoking via
broker-specific queue introspection for the risk it would add of purging something unintended.
Nothing in the demo's actual workflows can queue an expensive or long-running job.

### Cache / Redis cleanup

Deliberately does **not** run `FLUSHALL` or touch Redis at all. Two categories of state live
there: throttle counters (`docs/SECURITY.md` "Rate limiting") — never reset, on purpose, so a
reset can never become a way for an abusive client to reset its own rate-limit budget — and the
analytics dashboard cache (`apps.analytics.caching`, `ANALYTICS_CACHE_TTL_SECONDS`, 60 seconds by
default), which self-heals within its own short TTL and already tolerates a cache-backend read/
write failure by falling back to a direct query, making explicit invalidation unnecessary
complexity for a cosmetic ≤60-second staleness window. Django's built-in Redis cache backend
(`django.core.cache.backends.redis.RedisCache`, used here) has no pattern/wildcard delete
primitive in the first place — implementing one would mean bypassing Django's cache abstraction
entirely for this single, low-value case.

### Backup behavior

- **Manual reset** (`scripts/demo reset-demo --confirm`): does **not** automatically create a
  backup. Request one explicitly first if desired: `scripts/demo backup && scripts/demo
  reset-demo --confirm`.
- **Scheduled reset**: never creates a backup automatically, deliberately — a backup on every
  6-hourly run would accumulate without bound on a disposable demo host's disk. Routine
  backups (if wanted at all for a fully disposable public demo) are a separate, independently
  scheduled job with its own retention policy — not something a data-reset command should also
  own.
- **Retention**: none implemented by the reset path itself, for the reason above. If an operator
  adds scheduled backups separately, they are responsible for that job's own retention/rotation.

### Recovery after a failed reset

A failed reset (`DEMO RESET FAIL`, non-zero exit) means the entire attempt rolled back — the demo
is in exactly the state it was in before the attempt, never a half-reset state (see "Safety
guards" above). Do not immediately rerun destructive commands blindly:

1. Read the logged error — every failure logs a specific reason (a guard refusal, "already in
   progress", or the exception from whatever step failed) before printing `DEMO RESET FAIL`.
2. If it was a guard refusal (missing flag, missing organization), fix the configuration and
   retry `scripts/demo reset-demo --confirm`.
3. If it was "already in progress", another reset (manual or scheduled) is genuinely running —
   wait for it to finish and check whether it itself succeeded before retrying.
4. If it was a genuine error during the delete/reseed/verify phase, `scripts/demo health` first —
   confirm the application itself is still healthy (it should be; the failed transaction rolled
   back). If the error recurs on retry, this is a real bug or data-integrity issue, not a
   transient failure — escalate rather than repeatedly retrying, and consider §4's heavier
   snapshot-restore procedure as a fallback only if a real backup exists to restore from.
