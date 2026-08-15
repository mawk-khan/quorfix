# Access and Manual Testing Guide

> Update this document whenever a phase changes routes, credentials, roles, setup commands, demo data, or available functionality.

This is the permanent reference for logging into a local Quorfix instance and manually
exercising everything that has been built so far. It is updated at the end of every completed
phase or chunk (see the "Completed phases" section below), per the working-procedure rule in
[CLAUDE.md](../CLAUDE.md).

## Application URLs

All URLs below assume the default local Docker Compose ports (see `docker-compose.yml`).

| Purpose | URL |
| --- | --- |
| Frontend (Next.js) | http://localhost:3000 |
| Dashboard (home) | http://localhost:3000/ |
| Sign in | http://localhost:3000/sign-in |
| Initial setup (first run only) | http://localhost:3000/setup |
| Projects | http://localhost:3000/projects |
| Bugs | http://localhost:3000/bugs |
| Bug detail (comments, mentions, attachments, activity) | http://localhost:3000/bugs/{id} |
| Team / invitations | http://localhost:3000/team |
| Notifications | http://localhost:3000/notifications |
| Notification preferences | http://localhost:3000/notifications/preferences |
| Backend health | http://localhost:8000/api/health/ |
| Frontend-proxied backend health | http://localhost:3000/api/health/ |
| Backend API docs (OpenAPI/Swagger) — requires sign-in | http://localhost:8000/api/docs/ |
| Backend admin | http://localhost:8000/admin/ |

The frontend proxies every `/api/*` request to the backend (see `frontend/next.config.ts`), so in
normal use the browser only ever talks to `localhost:3000`.

## Local startup

```bash
docker compose up -d
docker compose ps
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo
```

Or, using the Makefile:

```bash
docker compose up -d
docker compose exec backend python manage.py migrate
make seed-demo
```

`seed_demo` is idempotent (safe to re-run) and, under production-hardened settings
(`ENVIRONMENT=production`, e.g. `docker-compose.prod.yml`), refuses to run at all unless
`QUORFIX_DISPOSABLE_DATABASE=true` and `DEMO_ADMIN_PASSWORD` are both explicitly set — see
[docs/DEMO_DEPLOYMENT.md](./DEMO_DEPLOYMENT.md) for the full production/demo seeding procedure.
Local development (this section) is unaffected — no extra flags needed.

## Reset and reseed

**Warning: this deletes all local development data**, including every organization, user,
project, bug, comment, and attachment file. Never run this against a shared, staging, or
production environment — only against your own local Docker Compose stack.

```bash
docker compose down -v
docker compose up -d
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo
```

`down -v` removes the named `postgres_data` volume (see `docker-compose.yml`), which is what
actually discards the data — a plain `docker compose down` does not.

**Never run the reset procedure against staging or production.**

## Backup and restore

See [docs/BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md) for the full PostgreSQL and local
attachment backup/restore runbook (`scripts/backup.sh`, `scripts/restore_db.sh`,
`scripts/restore_attachments.sh`).

**Warning:** against `docker-compose.prod.yml` specifically, `docker compose -f
docker-compose.prod.yml down -v` deletes the `postgres_data` **and** `attachments_data` named
volumes — all database and attachment data, not just Postgres. Never run this against a real
deployment without a verified, current backup (see "Backup verification" in
[docs/BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md)).

To rehearse a restore with zero risk to real data, run the disposable end-to-end restore drill
described in "Full restore procedure" in
[docs/BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md) — it uses its own disposable Compose
volumes and is never run against your normal development stack.

## Upgrading

See [docs/UPGRADING.md](./UPGRADING.md) for the full upgrade, migration, and rollback
procedure (support policy, pre-upgrade checks, `make prod-upgrade-check`/`make
upgrade-smoke`, and the rollback decision tree).

**Warning:** once a migration has actually run, rolling back to the previous code image
alone may not be safe — the previous code was never tested against the new schema. Per
`docs/UPGRADING.md`'s migration audit, essentially no migration in this codebase today has a
verified-reversible rollback path; the default, documented rollback mechanism is restoring
the pre-upgrade backup (see "Rollback decision tree" in `docs/UPGRADING.md`), which discards
any writes made after that backup was taken.

To rehearse an upgrade with zero risk to real data, run the disposable end-to-end upgrade
drill described in `docs/UPGRADING.md` — like the restore drill above, it uses its own
disposable Compose volumes (via an isolated `git worktree` for the prior-version source) and
is never run against your normal development stack.

## Continuous integration

Four GitHub Actions workflows (`.github/workflows/`) enforce the release-readiness baseline:
`backend.yml`, `frontend.yml`, `e2e.yml`, and `images.yml` (production image build validation
— builds only, never pushes). `release.yml` is a dormant skeleton that only triggers on a
`vX.Y.Z` tag push; nothing in the repository's history has created one.

Local commands mirroring each workflow (see README.md's "Continuous integration" section, or
each workflow file itself, for the authoritative exact sequence):

```bash
make ci-backend         # requires: docker compose up -d db redis backend celery_worker
make ci-frontend        # requires: docker compose up -d frontend
make ci-e2e             # see warning below
make ci-images          # builds only, never pushes
make openapi-check
make community-check
```

**Warning:** `make ci-e2e` (and the `e2e.yml` workflow it mirrors) is destructive to whatever
is currently in the dev stack's database — `frontend/e2e/global-setup.ts` flushes it and
reseeds only the deterministic, namespaced E2E fixtures (`seed_e2e_bug_fixture`,
`seed_e2e_analytics_fixture`), not your own local dev data. `scripts/ci_e2e.sh` backs up and
restores your `.env` automatically and always tears the stack down (including its volumes)
when it finishes, but the reset itself is real and happens every run — never point
`SKIP_E2E_DB_RESET=true` at a database you want to keep, and don't run `make ci-e2e` while you
have local dev data in the same stack that you still need.

## Demo login accounts

Produced by `python manage.py seed_demo` (`backend/apps/core/management/commands/seed_demo.py`).
**Development-only accounts — never reuse these credentials anywhere but a local development
environment, and they are never seeded or exposed in production** (the command refuses to run
under production settings).

| Role | Email | Password |
| --- | --- | --- |
| Administrator | admin@quorfix.local | QuorfixDemo2026! |
| Developer | developer@quorfix.local | DeveloperDemo2026! |
| QA | qa@quorfix.local | QADemo2026! |
| Reporter | reporter@quorfix.local | ReporterDemo2026! |
| Viewer | viewer@quorfix.local | ViewerDemo2026! |

`seed_demo` also creates three projects (`BFW`, `MOB`, `API`) with 24 demo bugs spread across
every status, priority, and severity, backdated across roughly the previous 45 days so the
dashboard (see below) has a meaningful trend to chart — and prints these credentials to the
console on each run (development settings only).

## Backend admin (Django) access

No account is seeded with `is_staff`/`is_superuser` by default — none of `seed_demo`,
`seed_e2e_bug_fixture`, or `seed_e2e_analytics_fixture` grant Django-admin access, only
application-level organization roles. To sign in at http://localhost:8000/admin/, create one
explicitly:

```bash
docker compose exec backend python manage.py createsuperuser
```

No app registers any models with the Django admin site (there is no `admin.py` under any
`backend/apps/*`), so the admin index is effectively empty after signing in — this gives you
Django's login and the default `auth`/`sessions` framework views only, not a browsable view of
Quorfix's own data. Use `/api/docs/` or `manage.py shell` to inspect application data instead.

`POST /admin/login/` is throttled at the application layer (10 failed attempts / 5 minutes per
client IP — see `apps.core.middleware.admin_login_throttle`, `docs/SECURITY.md` "Rate
limiting"), independently of the DRF-only scopes above. Repeatedly testing wrong credentials
locally will trip this the same way it would in production.

See [docs/INSTALLATION.md](./INSTALLATION.md) for the same command in the context of a fresh
install.

## E2E fixture accounts (for manual review)

Two additional, independently-namespaced account sets exist purely for the Playwright suite,
but work identically for manual sign-in and are often the fastest way to poke at a specific
role without touching your own `seed_demo` data. **Development-only, same production refusal
guarantee as `seed_demo`.**

Seed them with:

```bash
docker compose exec backend python manage.py seed_e2e_bug_fixture
docker compose exec backend python manage.py seed_e2e_analytics_fixture
```

Both are idempotent and safe to run alongside `seed_demo` — each seeds its organization with
`is_active=False`, which is the one flag Community's single-active-organization check
(`OrganizationPolicy.can_create_additional_organization()`) looks at, so these fixtures never
trip `seed_demo`'s "a different organization already exists" refusal or count against the
one-active-org limit. They remain fully functional for sign-in and every bug/project operation
regardless.

**Bug E2E Org** (`bug-e2e-org`, project `BEP`) — from `seed_e2e_bug_fixture`:

| Role | Email | Password |
| --- | --- | --- |
| Administrator | bug-e2e-admin@example.com | BugE2EPass123! |
| Developer | bug-e2e-developer@example.com | BugE2EPass123! |
| QA | bug-e2e-qa@example.com | BugE2EPass123! |
| Reporter | bug-e2e-reporter@example.com | BugE2EPass123! |
| Viewer | bug-e2e-viewer@example.com | BugE2EPass123! |

**Analytics E2E Org** (`analytics-e2e-org`, project `ANLY`, pre-populated with 8 backdated bugs
across every status — useful for exercising the dashboard without waiting on demo data) — from
`seed_e2e_analytics_fixture`:

| Role | Email | Password |
| --- | --- | --- |
| Administrator | analytics-e2e-admin@example.com | AnalyticsE2EPass123! |
| Developer | analytics-e2e-developer@example.com | AnalyticsE2EPass123! |
| QA | analytics-e2e-qa@example.com | AnalyticsE2EPass123! |
| Reporter | analytics-e2e-reporter@example.com | AnalyticsE2EPass123! |
| Viewer | analytics-e2e-viewer@example.com | AnalyticsE2EPass123! |

If you're seeding these on a database the E2E suite has also touched (rather than a plain
`seed_demo` install), reset `SetupLock` the same way `frontend/e2e/global-setup.ts` does before
reseeding, or first-run `/setup` will stay blocked:

```bash
docker compose exec backend python manage.py shell -c \
  "from apps.organizations.models import SetupLock; SetupLock.objects.get_or_create(id=1)"
```

## Role matrix

Reflects the actual backend authorization rules (`apps/bugs/policies.py`,
`apps/comments/policies.py`, `apps/attachments/policies.py`), not assumptions. The frontend's
role-based UI is a convenience layer only — every rule below is enforced server-side regardless of
what the UI shows.

Administrator, Developer, and QA are jointly "staff" roles on bugs
(`apps.bugs.policies.STAFF_ROLES`) — all three share identical bug-workflow authority: any of
them may transition a bug to any status the bug's current state allows (the valid next statuses
come from the bug's own state machine, not the role) and may assign a bug to any staff member
(`can_assign_bug`/`is_eligible_assignee_role`, `ASSIGNABLE_ROLES = STAFF_ROLES`). Archiving a bug
is administrator-only (`can_archive_bug`).

**Administrator**
- Organization and team administration (invite/remove members, change roles)
- Full project management (create, edit, archive/restore)
- Full bug workflow: create, transition to any status the bug's current state allows, assign to
  any staff member, archive/restore (archive is administrator-only)
- Comment moderation: delete any comment, redact any comment (including on an archived bug/project)
- Attachment moderation: remove any attachment (including after archive)
- Notifications and preferences

**Developer**
- View projects
- Create bugs and transition them to any status their current state allows (same authority as
  administrator and QA — cannot archive)
- Assign bugs to any staff member (administrator, developer, or QA)
- Comment and mention teammates
- Upload their own attachments; remove their own attachments while the bug/project are mutable
- Notifications and preferences

**QA**
- View projects
- Create bugs and transition them to any status their current state allows (same authority as
  administrator and developer — cannot archive)
- Assign bugs to any staff member (administrator, developer, or QA)
- Comment and mention teammates
- Upload their own attachments; remove their own attachments while mutable
- Notifications and preferences

**Reporter**
- Create bugs
- Edit their own bugs' content fields (title, description, steps to reproduce, expected/actual
  result, environment, category) only while the bug is still `new` or `triaged`
  (`REPORTER_EDITABLE_STATUSES`) — cannot set due date, priority, or severity (staff-only fields)
- Reopen their own bugs from any terminal status (resolved, closed, duplicate, cannot reproduce,
  won't fix) — the only status transition a reporter may apply, and only on their own bug
- Comment and mention teammates
- Upload their own attachments; remove their own attachments while mutable
- Notifications and preferences
- Cannot assign bugs or manage bug relationships (staff-only)

**Viewer**
- Read-only access to projects and bugs
- Watch bugs
- Read comments (no comment form is shown)
- Download attachments (no upload control is shown)
- Receive notifications
- No create, edit, comment, or upload actions anywhere

## Dashboard

The dashboard is the Community home page (`/`) — every authenticated role, including Viewer, can
open it; there are no mutation controls on the page itself, only filters and links out to
`/bugs` and `/projects`.

### Filters

- **Date range**: `Last 7 days` / `Last 30 days` (default) / `Last 90 days` / `Custom`. A preset
  means "today plus the previous N-1 calendar days" — Last 7 days is a 7-day inclusive span
  (today and the previous 6 days), never an accidental 8-day range. Presets are recomputed from
  the current date on every load, so a bookmarked `?range=7d` link always means "the last 7 days
  as of whenever it's opened" — only `Custom` stores literal `from`/`to` dates in the URL, since
  those are meant to stay fixed.
- **Custom range** accepts any `date_from <= date_to` pair up to **366 days inclusive**. Longer
  or reversed ranges are rejected with a structured error, both in the UI (before any request is
  sent) and by the backend (the authoritative check). 366 days is a deliberate Community ceiling:
  daily-bucketed trend queries stay cheap at that size, and longer historical analysis is
  Professional's "advanced analytics" territory, not this dashboard's job.
- **Project**: narrows every section that accepts a project filter to one project, or "All
  projects".

Both filters are kept in the URL's query string, so a filtered view can be bookmarked or shared
and reloading the page restores the exact same filters.

### Point-in-time vs. date-ranged sections

Not every section responds to the date range — only the sections where "in this time window"
is a meaningful question do:

| Section | Date range applies? | Project filter applies? |
| --- | --- | --- |
| Summary: Total open bugs, Overdue bugs | No (current snapshot) | Yes |
| Summary: New bugs, Resolved bugs | Yes | Yes |
| Bug Trends (created/resolved per day) | Yes | Yes |
| Average Resolution Time by priority | Yes | Yes |
| Bugs by Status | No (current backlog) | Yes |
| Bugs by Severity | No (current backlog) | Yes |
| Bugs per Developer (workload) | No (current, explicitly "who's carrying what right now") | Yes |
| Recent Activity | No (always the most recent, bounded) | Yes |
| Active Projects | No | No (it's the project list itself) |

Sections that ignore the date range say so directly under their heading ("Current backlog — not
affected by the date range", etc.) — the date filter never silently does nothing without saying so.

### Metric definitions

- **Open bugs**: status is one of `new, triaged, assigned, in_progress, ready_for_qa, reopened,
  blocked, deferred`. Terminal statuses (`resolved, closed, duplicate, cannot_reproduce,
  wont_fix`) are never counted as open.
- **Overdue bugs**: an open bug whose `due_date` is before today.
- **Archived bugs, and bugs belonging to an archived project, are excluded from every dashboard
  section by default** — the dashboard shows what currently needs attention, not the full
  archive.
- **New bugs**: count of bugs whose `created_at` falls in the selected range.
- **Resolved bugs (summary card + Bug Trends line)**: a *throughput* measure — counts every
  resolution-transition event (status changed to `resolved`, `duplicate`, `cannot_reproduce`, or
  `wont_fix`) that happened in the selected range, using the bug's immutable activity history.
  Closing a bug is not counted as a second resolution event. Because this reads from history
  rather than current state, **a bug that was resolved and later reopened still counts on the day
  it was originally resolved** — reopening it doesn't erase that it happened.
- **Average Resolution Time by priority**: a *duration* measure, answering a different question
  than the throughput count above — "for work that's still resolved right now, how long did it
  take?" Start is `created_at`; end is the bug's *current* `resolved_at` (not `closed_at` —
  closing is a separate, often-later administrative step). Only bugs whose current status is
  `resolved`, `duplicate`, `cannot_reproduce`, or `wont_fix` are included, and only when
  `resolved_at` falls in the selected range. **A bug that is currently reopened is excluded** —
  its `resolved_at` is null until it's resolved again, so it has no current answer to "how long
  did it take." These two metrics are intentionally different: the trend/summary count answers
  "how much resolution work happened," the duration answers "how long did work that's still
  resolved take" — a bug can appear in one and not the other in the same range.
- **Bugs per Developer (workload)**: current open-bug count (see Open bugs above) grouped by
  assignee.
  - **Unassigned**: bugs with no assignee at all.
  - **Needs reassignment**: bugs whose assignee's *current* organization role is no longer
    eligible for assignment (Reporter or Viewer) — this happens when an administrator changes
    someone's role without reassigning their bugs first, not when a member is removed (removing a
    member automatically clears their assignments to Unassigned instead). Needs-reassignment bugs
    are never hidden and never folded into Unassigned — they're shown separately, by name, so
    nothing silently disappears from view.
- **Active Projects**: every non-archived project, with its total (non-archived) bug count and
  current open-bug count.

### Known Community limitations

- Date-range boundaries use the server's configured timezone (UTC), not a per-organization
  timezone — Community does not yet store one. A custom range's `date_from`/`date_to` are
  interpreted as UTC calendar days.
- Dashboard data can lag up to **60 seconds** behind the very latest change — most sections are
  cached for 60 seconds to keep the page fast (Recent Activity is never cached, so it always
  reflects the latest event). A Redis outage does not break the dashboard; it falls back to
  direct database queries.
- No percentage-change / trend-vs-previous-period indicators in Community — the summary cards
  show authoritative current totals only.
- No custom report builder, saved dashboard layouts, scheduled reports, cross-organization
  reporting, SLA analytics, forecasting, custom metrics, or CSV/PDF export — all Professional.

## Completed phases

### Phase 0: Scaffold
- **Status:** Complete
- **Commit:** `171e0de`
- **Main functionality:** Django + Next.js modular monolith foundation, Docker Compose stack, CI scaffolding.
- **URLs:** N/A (no user-facing routes yet).
- **Manual test steps:** `docker compose up -d`, confirm all containers report healthy (`docker compose ps`).
- **Known limitations:** No application functionality yet.

### Phase 1: Accounts and organizations
- **Status:** Complete
- **Commit:** `22b05f1` (demo-data seeding groundwork added in `d4533ca`)
- **Main functionality:** Authentication (session cookies + CSRF), first-run organization setup, invitations, roles, membership management.
- **URLs:** `/setup`, `/sign-in`, `/team`.
- **Manual test steps:** Complete `/setup` once on a fresh database; sign in; invite a teammate from `/team` and accept the invitation link.
- **Known limitations:** Single active organization only (Community restriction — see CLAUDE.md).

### Phase 2: Projects
- **Status:** Complete
- **Commit:** `66c9516` (delivered together with Phase 3 — see below)
- **Main functionality:** Project creation, key/status/archive lifecycle, project list/detail.
- **URLs:** `/projects`, `/projects/new`, `/projects/{id}`.
- **Manual test steps:** Create a project, edit it, archive and restore it.
- **Known limitations:** No custom fields or saved views (Professional).

### Phase 3: Bug tracking
- **Status:** Complete
- **Commit:** `66c9516`
- **Main functionality:** Bug creation/management, standard workflow, assignment, status/priority/severity, tags, watchers, relationships, optimistic concurrency (`version`), basic activity history.
- **URLs:** `/bugs`, `/bugs/new`, `/bugs/{id}`.
- **Manual test steps:** Create a bug, transition it through its workflow, assign it, tag it, watch/unwatch it, archive/restore it, trigger a version conflict from two open tabs.
- **Known limitations:** No custom workflows or custom fields (Professional).

### Phase 4 Chunk 1: Comments and mentions backend
- **Status:** Complete (backend only — frontend added in Chunk 4)
- **Commit:** `1046538`
- **Main functionality:** Paginated comments, create/edit-within-window/delete, administrator delete-any/redact, structured `@[Name](mention:<uuid>)` mention syntax, tenant-isolated mention resolution, immutable activity records.
- **URLs:** Backend only at this point (`/api/bugs/{id}/comments/...`).
- **Manual test steps:** Exercise via `/api/docs/` or the frontend once Chunk 4 is in place (see below).
- **Known limitations:** No frontend UI (added in Chunk 4).

### Phase 4 Chunk 2: Local attachments backend
- **Status:** Complete (backend only — frontend added in Chunk 4)
- **Commit:** `35413ac`
- **Main functionality:** Local-disk two-step upload (initiate + authenticated byte upload), file validation (type allow-list + byte-signature check, 10 MB max, no SVG), paginated attachment list, authorized download, soft removal, administrator moderation after archive, asynchronous storage cleanup via Celery.
- **URLs:** Backend only at this point (`/api/bugs/{id}/attachments/...`).
- **Manual test steps:** Exercise via `/api/docs/` or the frontend once Chunk 4 is in place (see below).
- **Known limitations:** Local filesystem storage only — no S3-compatible provider yet.

### Phase 4 Chunk 3: Notifications
- **Status:** Complete
- **Commit:** `6c86f8d`
- **Main functionality:** Notification bell + `/notifications` + `/notifications/preferences`, mention/comment/assignment/status-change/reopen notification events, per-event email preferences, deduplication.
- **URLs:** `/notifications`, `/notifications/preferences`; the bell is present in the app shell on every authenticated page.
- **Manual test steps:** Trigger a mention or assignment as one user, confirm the recipient's bell count and `/notifications` list update; toggle an email preference off and confirm no further email is sent for that event type.
- **Known limitations:** No browser push notifications (out of scope for Community).

### Phase 4 Chunk 4: Collaboration frontend
- **Status:** Complete
- **Commit:** _(this change — update once committed)_
- **Main functionality:** Bug-detail discussion UI (list, create, edit, delete, administrator redact), `@`-mention picker with keyboard/mouse/accessible-listbox support and safe mention rendering, attachment upload UI with drag-and-drop, progress, and fresh-row retry, attachment list with download/remove, full integration into `/bugs/{id}` alongside the existing activity feed.
- **URLs:** `/bugs/{id}` (Attachments and Discussion sections).
- **Manual test steps:** See "Comment and mention lifecycle" and "Attachment lifecycle" in the checklist below.
- **Known limitations:** Mention suggestions search the first 100 organization members client-side (no backend search endpoint yet) — fine for Community's realistic team sizes, would need a real search endpoint at larger (Professional) scale. No rich-text editing, threading, or reactions on comments. No attachment previews.

### Phase 5: Community Dashboard and Basic Analytics
- **Status:** Complete
- **Commit:** _(this change — update once committed)_
- **Main functionality:** Organization-scoped dashboard at `/` — summary metrics, Bug Trends line
  chart, Average Resolution Time by priority, Bugs by Status, Bugs by Severity, Bugs per
  Developer (with a Needs-reassignment bucket), Recent Activity, and Active Projects. Date-range
  (7/30/90-day presets or custom, up to 366 days) and project filters, kept in the URL. Backend:
  `apps.analytics` — 7 focused, thin, PostgreSQL-aggregating endpoints under
  `/api/analytics/...`, short-TTL (60s) Redis caching with a direct-database fallback on any
  cache failure, tenant-isolated and capability-free (Community-only, no Professional dependency).
- **URLs:** `/` (replaces the previous placeholder home page).
- **Manual test steps:** See "Dashboard" in the manual test checklist below.
- **Known limitations:** See "Known Community limitations" under the Dashboard section above
  (server-timezone date boundaries, 60-second cache lag, no percentage-change indicators, no
  Professional reporting features).

### Phase 6 Chunk D: Backup and restore
- **Status:** Complete
- **Commit:** _(this change — update once committed)_
- **Main functionality:** PostgreSQL and local-attachment backup/restore for
  `docker-compose.prod.yml`, treated as one coordinated recovery set. `scripts/backup.sh`
  produces a timestamped `quorfix-backup-<UTC timestamp>/` directory
  (`manifest.txt`, `database.dump`, `attachments.tar.gz`, `checksums.sha256`);
  `scripts/restore_db.sh`/`scripts/restore_attachments.sh` restore one artifact each, both
  requiring an explicit `--confirm-restore` flag and validating checksum + manifest before
  mutating anything. Attachment-archive extraction is guarded against path traversal
  (`backend/apps/core/tar_safety.py`). No routes or user-visible functionality changed — this
  is operator tooling and documentation only.
- **URLs:** None (no application-facing change).
- **Manual test steps:** See "Full restore procedure" and the disposable end-to-end restore
  drill in [docs/BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md).
- **Known limitations:** Routine backups are not a transactionally synchronized
  database/attachments snapshot (see "Consistency limitations" in
  `docs/BACKUP_AND_RESTORE.md`) — a guaranteed-consistent snapshot requires a maintenance
  window. Retention and encryption-at-rest are documented as operator policy, not enforced by
  the tooling.

### Phase 6 Chunk E: Upgrade, migration, and rollback documentation
- **Status:** Complete
- **Commit:** _(this change — update once committed)_
- **Main functionality:** `docs/UPGRADING.md` — a conservative pre-1.0 upgrade support policy,
  a full migration audit (leaf nodes, `RunPython`/reversibility findings, lock-risk table), a
  step-by-step upgrade procedure using the actual `docker-compose.prod.yml` service names, an
  explicit rollback decision tree (before migrations / verified-reversible / uncertain-or-
  irreversible / new-writes-since-backup), and Celery task cross-version compatibility
  findings. New non-destructive Makefile targets `prod-migrations-check`,
  `prod-migrations-plan`, `prod-upgrade-check`, `prod-version`, `upgrade-smoke`;
  `scripts/upgrade_smoke.sh` (read-only container/health/migration-status check) and
  `scripts/inspect_version.sh` (OCI image label inspection). No routes or user-visible
  functionality changed — this is operator tooling and documentation only.
- **URLs:** None (no application-facing change).
- **Manual test steps:** See the disposable end-to-end upgrade drill in
  [docs/UPGRADING.md](./UPGRADING.md).
- **Known limitations:** No migration in the current codebase has a verified-reversible
  rollback path (see the migration audit in `docs/UPGRADING.md`) — rollback after migrations
  defaults to restoring the pre-upgrade backup, which discards writes made after that backup.
  Rolling/mixed-version deployment is not supported before 1.0.

### Phase 6 Chunk F: CI hardening, dependency scanning, OpenAPI validation, and release-build verification
- **Status:** Complete
- **Commit:** _(this change — update once committed)_
- **Main functionality:** `backend.yml` now runs Ruff format check, a Django system check,
  migration drift + unapplied checks, OpenAPI generation+validation, an explicit
  Community-only verification step, and a non-blocking pip-audit dependency scan.
  `frontend.yml` switched from `npm install` to `npm ci` and added a blocking `npm audit
  --audit-level=high` (current baseline: 0 vulnerabilities). `e2e.yml` was reworked to run the
  full stack via `docker compose` instead of raw background processes — this fixed two real,
  pre-existing gaps found during the audit: `dashboard.spec.ts`'s required
  `seed_e2e_analytics_fixture` was never seeded in CI, and the workflow set
  `SKIP_E2E_DB_RESET=true`, bypassing `global-setup.ts`'s real reset path entirely. New
  `images.yml` builds both production images (never pushes), verifies non-root runtime users,
  and runs a minimal container smoke check. New dormant `release.yml` skeleton (tag-triggered
  only, never runs on its own). New `scripts/ci_backend.sh`, `ci_frontend.sh`, `ci_e2e.sh`,
  `ci_images.sh`, wired to new Makefile targets (`ci-backend`, `ci-backend-audit`,
  `ci-frontend`, `ci-e2e`, `ci-images`, `openapi-check`, `community-check`). No routes or
  user-visible functionality changed — this is CI/tooling and documentation only.
- **URLs:** None (no application-facing change).
- **Manual test steps:** See "Continuous integration" above for local command equivalents to
  every workflow.
- **Known limitations:** pip-audit currently finds real, actionable findings against Django
  5.1.6 (fixed in 5.1.15+) — non-blocking in CI by policy, tracked here as a follow-up
  dependency upgrade, not fixed in this chunk. `release.yml`'s actual push path has never been
  exercised (no registry/tag has ever been created) — it is a reviewed-but-unrun skeleton.

### Phase 6 Chunk G: Dependency remediation and focused Community security hardening
- **Status:** Complete
- **Commit:** _(this change — update once committed)_
- **Main functionality:** Django upgraded 5.1.6 → 5.1.15 (latest secure 5.1.x patch),
  resolving all 20 advisories from Chunk F's baseline — `pip-audit` is now clean and
  **blocking** in `backend.yml` (the `continue-on-error` from Chunk F was removed; the separate
  `ci-backend-audit` Makefile target was folded into `ci-backend` since it's no longer a
  distinct CI step). New `frontend/next.config.ts` `headers()`: CSP, `X-Content-Type-Options`,
  `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy` on every response — no HSTS
  (documented as the reverse proxy's responsibility). New throttle scopes
  `invitation-create` (20/hour) and `attachment-upload` (30/min); bug/comment creation
  deliberately left unthrottled (see `docs/SECURITY.md` "Rate limiting" for the full
  reasoning). New `docs/SECURITY.md` (placeholder contact — see its own top note and
  README.md). Audited tenant isolation, attachment security, comment/mention rendering,
  notification security, and production logging — found and closed one real gap (the
  `/api/bugs/{id}/activity/` endpoint had no cross-organization isolation test, though the
  code itself was already correctly scoped) and one real test-coverage gap (nothing verified
  the *real*, committed `config.settings.production` module's cookie/session values, only
  synthetic `override_settings()` stand-ins — new
  `backend/apps/core/tests/test_production_settings_real_values.py`). No routes or
  user-visible functionality changed beyond the new response headers — this is a security
  hardening and dependency-remediation pass.
- **URLs:** None (no new application-facing routes; response headers apply everywhere).
- **Manual test steps:** `curl -I` any page and confirm the headers above; see
  `docs/SECURITY.md` for the full security model.
- **Known limitations:** `pytest` (a dev-only tool, never shipped in production images) has
  one open advisory (PYSEC-2026-1845, fixed in 9.0.3) found while auditing
  `requirements-dev.txt` — out of this chunk's explicit scope (`backend/requirements.txt`) and
  outside what `backend.yml`'s pip-audit step scans; noted here rather than silently dropped.
  No malware/virus scanning of uploaded attachments exists in Community (documented, not new).

### Phase 6 Chunk H: Community accessibility audit and remediation
- **Status:** Complete
- **Commit:** _(this change — update once committed)_
- **Main functionality:** Audited and remediated accessibility across the full Community
  interface. Added a shared `AlertDialog` primitive (proper `role="alertdialog"`,
  `aria-modal`, initial focus on Cancel — never the destructive action, a Tab focus trap,
  Escape-to-close, and focus restored to the triggering button on close) and replaced four
  duplicated, broken inline confirmation panels with it (comment delete/redact, attachment
  remove, bug/project archive) — each passes a `restoreFocusTo` ref captured by its own trigger
  button, rather than `AlertDialog` reading `document.activeElement` itself: every real call
  site renders the trigger and the dialog as mutually exclusive siblings, so the trigger has
  already unmounted (and the ref is already `null`) by the time the dialog's own mount effect
  would run. The Playwright keyboard suite caught this exact bug in the first implementation
  (`e2e/keyboard-navigation.spec.ts`'s "cancels a destructive dialog..." case) — retained as a
  standing regression test, alongside a matching component test whose harness unmounts the
  trigger the same way. Added a "Skip to main content" link and `aria-current="page"`
  on the primary nav; every page's `<main>` now carries `id="main-content" tabIndex={-1}` and
  client-side route changes move focus there automatically (Next's App Router does not do this
  itself). Fixed `NotificationBell`'s dropdown to use `aria-controls`/a real `id` linking
  trigger to panel. Added `aria-invalid`/`aria-describedby` error association (a new
  `errorProps()` helper) to every form field with an active validator, across sign-in, setup,
  invitation-accept, bug create/edit, project create/edit, and team invite. Replaced
  `role="alert"` on static sign-in-required/not-found/forbidden page states with a new shared
  `AccessState` component (a real heading + plain text + a next-action link) — those are
  page-load conditions, not dynamic interruptions, so an assertive announcement on every visit
  was spurious; genuine dynamic mutation-error alerts were left untouched. Added focus
  restoration after comment-edit cancel/save (the Edit button, since the textarea unmounts) and
  a "Saved." status after bug/project content-edit submissions. Converted attachment upload
  progress to `role="progressbar"` with `aria-valuenow/min/max`, associated the accepted-types
  hint with the file input via `aria-describedby`, and added an `aria-live` result-count
  announcement to the mention-suggestion popover. Added `<caption>` to the bugs, projects, and
  team-member tables. Added `@axe-core/playwright` (dev-only) and
  `frontend/e2e/accessibility.spec.ts`, scanning sign-in (unauthenticated), dashboard, projects,
  bugs, bug detail, notifications, and notification preferences — failing on any
  serious/critical violation with no rules disabled; it caught one real defect (muted caption
  text, `text-gray-400` on white, at 2.6:1 contrast — fixed to `text-gray-500`, ~4.8:1). Added
  `frontend/e2e/keyboard-navigation.spec.ts` (keyboard-only sign-in, skip link, bug creation,
  notification dropdown, and destructive-dialog cancel with focus restoration) and component
  tests for `AlertDialog`, `AppShell` (skip link, `aria-current`, route-change focus), and the
  notification dropdown's `aria-controls` wiring. Added a global
  `prefers-reduced-motion: reduce` rule. Fixed `VisuallyHiddenTable` (found during narrow-
  viewport verification, see "Known limitations" below): `sr-only` moved from the `<table>`
  itself onto a wrapping `<div>`, since a `clip-path`-hidden table doesn't shrink its own layout
  box the way an ordinary element does.
- **URLs:** None (no new application-facing routes).
- **Manual test steps:** See "Accessibility" under "Manual test checklist" below.
- **Known limitations:** This automated + manual pass is not a WCAG conformance certification —
  axe-core catches roughly a third of WCAG success criteria by nature (anything requiring human
  judgment — meaningful alt text quality, logical reading order, cognitive load — is out of its
  reach). **No live screen-reader (NVDA/JAWS/VoiceOver/Orca) pass was performed** — none is
  available in this headless Linux sandbox, so section 9 of the review below is explicitly not
  claimed complete; a human with real AT access still needs to do this. 200%-zoom (simulated as
  a 640×480 viewport) and a 375×667 narrow viewport were verified concretely, not just reviewed
  at the code level: `document.documentElement.scrollWidth` was checked for horizontal overflow
  on the dashboard, bugs list, bug detail, and new-bug form. This caught one real defect —
  `VisuallyHiddenTable` applied Tailwind's `sr-only` directly to a `<table>` element; a
  `clip-path`-based hide (Tailwind v4's implementation) doesn't shrink a table's own layout box
  the way it does an ordinary element, so the hidden table still contributed ~250px of real
  width, causing 19px of horizontal page overflow on a 375px-wide viewport specifically on the
  dashboard (`frontend/src/app/visually-hidden-table.tsx`). Fixed by moving `sr-only` onto a
  wrapping `<div>` instead — verified back to 0px overflow afterward. `prefers-reduced-motion:
  reduce` was verified to actually collapse `animation-duration`/`transition-duration` to
  `0.01ms` via `page.emulateMedia()`, not just reviewed as a CSS rule in isolation. The
  keyboard-only pass itself was exercised via the automated `keyboard-navigation.spec.ts`
  scenarios (5 real Chromium sessions), not a separate live human click-through — a human pass
  is still worth doing for the flows those 5 scenarios don't cover (e.g. comment editing,
  attachment upload, tag add/remove).

### Phase 6 Chunk J: Structured logging, request correlation, and operational observability
- **Status:** Complete
- **Commit:** _(this change — update once committed)_
- **Main functionality:** See `docs/OBSERVABILITY.md` for the full reference. Summary: every
  HTTP request now gets a correlation ID (`X-Request-ID` request header when syntactically
  safe, otherwise generated), echoed back on the response and attached to every log line
  emitted during that request via a new `RequestIdMiddleware` + `RequestContextFilter`
  (`backend/apps/core/middleware/request_id.py`, `backend/apps/core/log_context.py`).
  Production logs are structured JSON by default (configurable via new `LOG_FORMAT`/
  `LOG_LEVEL`/`SERVICE_NAME`/`REQUEST_ID_HEADER` settings); development/test stay
  human-readable. Celery tasks (`create_notifications_for_event`, `send_notification_email`,
  `delete_attachment_object`) now receive the dispatching request's correlation ID via task
  headers (`apps.core.task_correlation`) — no task call signature or dedup-key behavior
  changed. Added safe login/logout/setup/invitation-acceptance logging (no passwords, tokens,
  or emails — see `docs/OBSERVABILITY.md` "Sensitive-data policy"). Attachment failure logs now
  reference a non-reversible storage-key hash instead of the raw key. An automated static scan
  (`backend/apps/core/tests/test_logging_security.py`) now fails CI if any future logger call
  references a forbidden identifier (password, secret key, session/CSRF token, raw invitation
  token). Optional request-completion timing log added
  (`RequestLoggingMiddleware`: method, route, status, duration — never the query string or
  body). No routes, roles, credentials, or demo data changed.
- **URLs:** None (no new application-facing routes). `X-Request-ID` is a new request/response
  header on every existing route.
- **How to inspect logs:**
  ```sh
  docker compose logs -f backend         # application + Django + gunicorn.error
  docker compose logs -f celery_worker   # Celery task logs
  ```
- **How to search by request ID:** read `X-Request-ID` from a response (browser DevTools →
  Network → Response Headers, or `curl -i`), then:
  ```sh
  docker compose logs backend | grep '<request-id>'
  ```
  See `docs/OBSERVABILITY.md` "Troubleshooting examples" for the gunicorn-access-log and
  Celery-task variants.
- **Known limitations:** see `docs/OBSERVABILITY.md` "Known limitations" — gunicorn's access-log
  correlation lives in the pre-rendered message text (a `rid=` atom), not a structured
  `request_id` field, since that log line is written after `RequestIdMiddleware`'s own context
  has already cleared; no metrics/tracing integration exists yet.

### Phase 6 Chunk K: Quorfix branding migration and Community release documentation
- **Status:** Complete
- **Commit:** _(this change — update once committed)_
- **Product name:** Quorfix (renamed from this project's pre-launch working title).
- **Official domain:** quorfix.com *(not yet confirmed live — do not assume DNS/TLS/email/hosting
  are configured; see `docs/INSTALLATION.md` "Required origins")*.
- **Official repository:** https://github.com/mawk-khan/quorfix
- **Current version:** `0.5.0-beta.1` (see root `VERSION` file — the single source of truth;
  not yet tagged).
- **Main functionality:** A full audit of every old-branding match across the tracked tree
  classified each one before anything changed — see this chunk's own completion report for the
  full table. Every occurrence was replaced, including identifiers initially kept for
  compatibility during the rename: the disposable-database guard env var is now
  `QUORFIX_DISPOSABLE_DATABASE`, demo emails are `@quorfix.local`, `docker-compose.yml`'s Compose
  project name is `quorfix` (the local dev stack was brought down and back up under the new
  project name; the pre-rename `postgres_data` volume was left on disk, unused, rather than
  migrated), `seed_demo` looks up only the current `quorfix-demo` organization slug, and
  `scripts/backup.sh` only documents the `quorfix-backup-` prefix. Dropping the pre-rename demo
  organization slug lookup is a **pre-public-beta branding reset, not a supported migration
  path**: this project has no external users yet, so an old local checkout with a demo
  organization seeded under the old slug is not a case `seed_demo` needs to reconcile going
  forward — reset the local database (`docker compose down -v` and re-migrate) rather than relying
  on `seed_demo` to find or rename it. No Django app, migration, or table was touched. User-facing
  text (page titles,
  AppShell, setup/sign-in headings, invitation email subject, OpenAPI title/description, LICENSE
  copyright, system-check IDs `quorfix.E0xx`, `SERVICE_NAME`/Celery app name defaults, browser tab
  titles via a new `usePageTitle` hook — see `frontend/src/lib/use-page-title.ts`) says Quorfix.
  New root-level docs created: `docs/INSTALLATION.md`, `docs/RELEASING.md`,
  `THIRD_PARTY_NOTICES.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `.github/ISSUE_TEMPLATE/*`, `.github/PULL_REQUEST_TEMPLATE.md`. `.github/workflows/release.yml`
  hardened: validates the pushed tag equals `v$(cat VERSION)` (not just the `vX.Y.Z` shape), now
  requires `backend.yml`/`frontend.yml` to pass in full (via `workflow_call`) before building
  anything, smoke-tests the *actual* images about to be pushed (not a separately-built copy),
  and uses `quorfix-backend`/`quorfix-frontend` GHCR naming. `backend/requirements-dev.txt`'s
  `pytest` upgraded 8.3.4 → 9.1.1, resolving PYSEC-2026-1845 — `pytest-django` deliberately kept
  at 4.9.0 (4.13.0 has a reproducible incompatibility with pytest 9 against this project's own
  suite; see that file's own comment). Backend development-dependency `pip-audit` is now a
  second, separately-blocking CI step (previously unscanned in CI). No routes, roles, or API
  paths changed.
- **Demo credentials:** `admin@quorfix.local` / `QuorfixDemo2026!` (`seed_demo` reconciles the
  password idempotently on re-run, same as every other persona field). See the credentials table
  below.
- **Security contact status (as of this chunk):** still a placeholder — **release blocker**, see
  `docs/SECURITY.md`. Resolved in Phase 6 Chunk L (`security@quorfix.com`, confirmed monitored by
  the project owner) — see that chunk's entry below.
- **Code of Conduct contact status (as of this chunk):** still a placeholder — **release
  blocker**, see `CODE_OF_CONDUCT.md`. Resolved in Phase 6 Chunk L (`conduct@quorfix.com`,
  confirmed monitored by the project owner) — see that chunk's entry below.
- **Clean-install guide:** `docs/INSTALLATION.md`.
- **Release guide:** `docs/RELEASING.md` (procedure only — no release has been executed).
- **Contribution guide:** `CONTRIBUTING.md`.
- **Beta limitations:** see `CHANGELOG.md`'s `[0.5.0-beta.1]` entry for the full, versioned list
  (single organization per install, local-only attachment storage, UTC analytics boundaries,
  `OFFSET` deep-page cost, limited concurrent-load testing, no zero-downtime guarantee, reverse
  proxy/TLS required, no Professional features, no formal WCAG certification). The two contact
  blockers noted above were resolved in Phase 6 Chunk L.
- **Final local test commands for this chunk:**
  ```sh
  # Backend
  docker compose exec backend ruff format --check .
  docker compose exec backend ruff check .
  docker compose exec backend pytest
  docker compose exec backend pip-audit -r requirements.txt
  docker compose exec backend pip-audit -r requirements-dev.txt
  docker compose exec backend python manage.py makemigrations --check --dry-run

  # Frontend
  docker compose exec frontend npm run lint
  docker compose exec frontend npm run typecheck
  docker compose exec frontend npm test
  docker compose exec frontend npm run build
  docker compose exec frontend npm audit --audit-level=high

  # Docs / release tooling
  bash scripts/check_docs.sh
  bash scripts/check_version_consistency.sh
  bash scripts/tests/test_backup_restore_guards.sh

  # Docker (build only — never publishes)
  make ci-images
  ```

### Phase 6 Chunk L: Contact resolution and final release gate
- **Status:** Complete (contact resolution + gate audit); release itself not executed.
- **Commit:** _(this change — update once committed)_
- **Contacts resolved:** `security@quorfix.com` (vulnerability reports, `docs/SECURITY.md`) and
  `conduct@quorfix.com` (Code of Conduct enforcement, `CODE_OF_CONDUCT.md`) are confirmed,
  monitored addresses, approved for public use. Every placeholder-contact marker and "release
  blocker" framing referencing them was removed across `docs/SECURITY.md`, `CODE_OF_CONDUCT.md`,
  `README.md`, `docs/RELEASING.md`, `docs/ACCESS_AND_TESTING.md` (this file), `CHANGELOG.md`, and
  `.github/ISSUE_TEMPLATE/config.yml`. `scripts/check_docs.sh`'s check 6 was rewritten from
  "the placeholder marker is only in the expected files" to "no placeholder marker remains
  anywhere, and both confirmed addresses are present where required."
- **Full release-gate audit performed** against candidate `481073c` (plus this chunk's own
  contact-fix commit on top): backend (ruff/Django checks/migrations/pytest/community-only/
  OpenAPI/pip-audit ×2) — PASS; frontend (lint/typecheck/build/vitest/npm audit, mention-textarea
  stability re-verified 10 consecutive isolated runs + full suite ×3) — PASS; branding/version/
  docs — PASS; production images (uid 1000, correct OCI labels, smoke checks) — PASS; a full
  23-step clean-install drill via the real `/api/setup/` flow (not `seed_demo`) against
  `docker-compose.prod.yml` with fresh disposable volumes — PASS; security headers/cookies and
  tenant-isolation coverage across all 8 required apps — PASS; observability (generated/supplied/
  invalid request IDs, Celery task/correlation-ID propagation, JSON logs, zero health-check INFO
  flooding, zero secrets in logs) — PASS; backup/restore drill (destroy + restore, exact
  attachment checksum, non-standard-directory-name regression) — PASS; performance guards +
  representative measurement — PASS.
- **Full Playwright E2E and the axe-core accessibility scan were BLOCKED**, not skipped: this
  environment's Chromium cannot launch (`libasound.so.2` and other shared libraries are missing
  from the host, and no passwordless sudo is available to install them), and running the suite
  via GitHub Actions instead would require pushing the candidate commit first, which was not
  authorized this session. This is an explicit, tracked release blocker for the next attempt —
  not a pass.
- **Upgrade drill substitution:** the requested source commit for the upgrade gate predates
  `docker-compose.prod.yml`, `backend/Dockerfile`'s production stage, and every backup/restore
  script entirely — there was no production stack at that point in history to upgrade from. The
  drill was run instead from the earliest commit that has one (the one that introduced production
  container configuration), in an isolated git worktree, and passed in full: migration plan/apply,
  matching backend/worker images, old data and attachment-checksum survival, a real Celery task
  succeeding post-upgrade, and a rollback-via-backup-restore path that correctly reverted
  post-upgrade changes.
- **GitHub synchronization:** `origin` (`github.com/mawk-khan/quorfix`) was 2–3 commits behind
  local `master` for this entire chunk (nothing was pushed, per instruction) — every GitHub
  Actions-dependent verification is therefore itself blocked on a push happening first.
- **Overall verdict:** BLOCKED FOR v0.5.0-beta.1 — solely on the E2E/accessibility gate above.
  Every other gate in the audit passed. See this chunk's completion report for the full
  evidence table.

## Manual test checklist

**First-run setup**
1. On a freshly reset database, visit `/setup` and create the first organization + administrator account.
2. Confirm `/setup` refuses a second run once an organization exists.

**Admin sign-in**
1. Sign in at `/sign-in` with an administrator account.
2. Confirm the app shell, notification bell, and `/projects`/`/bugs` navigation are visible.

**Dashboard**
1. After signing in (any role), confirm you land on `/` and see the dashboard, not the old
   placeholder screen.
2. Confirm summary cards, Bug Trends, Average Resolution Time, Bugs by Status, Bugs by Severity,
   Bugs per Developer, Recent Activity, and Active Projects all render with data (run
   `seed_demo` first if the dashboard looks empty — see "Local startup" above).
3. Click each date-range preset (7/30/90 days) and confirm the summary's New/Resolved cards and
   the Bug Trends chart change, while Total open bugs, Overdue bugs, Bugs by Status/Severity,
   Bugs per Developer, and Active Projects stay the same (they're point-in-time, not date-ranged
   — see the Dashboard section above).
4. Switch to a custom range, enter an end date before the start date, and confirm a validation
   error appears without a request being sent. Enter a range longer than 366 days and confirm the
   same. Enter a valid custom range and confirm it applies.
5. Select a specific project from the project filter and confirm every filterable section narrows
   to that project; switch back to "All projects".
6. Confirm every chart has a visible legend/tooltip and that a screen reader (or browser dev
   tools' accessibility tree) exposes the same numbers via each chart's hidden data table.
7. Sign in as a Viewer and confirm the dashboard is fully visible with no create/edit controls.
8. Reload the page with filters applied (e.g. `/?range=7d&project=<id>`) and confirm the same
   filters are restored from the URL.

**Team invitation**
1. From `/team`, invite a new member with a specific role.
2. Open the invitation link (incognito/second browser) and accept it, setting a password.
3. Confirm the new member appears in `/team` with the correct role.

**Project lifecycle**
1. Create a project from `/projects/new`.
2. Edit its name/status.
3. Archive it, confirm it's excluded from default listings, then restore it.

**Bug lifecycle**
1. Create a bug against an active project.
2. Move it through its workflow transitions.
3. Assign it, tag it, add a relationship to another bug.
4. Watch/unwatch it.
5. Archive it, confirm the read-only state, then restore it.

**Comment and mention lifecycle**
1. As a non-viewer role, open a bug and post a comment.
2. Type `@` in the comment box, confirm the suggestion list opens, filter it by typing, and select
   a member with both keyboard (Arrow keys + Enter) and mouse in separate attempts.
3. Confirm the mentioned member receives exactly one `mentioned` notification (not also a
   duplicate `comment_added`).
4. Edit your own comment within 15 minutes; confirm the "(edited)" indicator appears.
5. Wait past the edit window (or use a comment older than 15 minutes) and confirm edit/delete are
   no longer offered, and that attempting them via a stale UI state surfaces the backend's error.
6. Delete your own comment; confirm the "This comment was deleted." placeholder replaces it
   immediately.
7. As an administrator, redact another user's comment; confirm the explicit moderation wording and
   that the body is replaced with the redaction placeholder.
8. As a viewer, confirm the discussion is visible but no comment form is rendered.
9. Archive the bug; confirm new comments are blocked with an explanation, while administrator
   redact/delete-any remain available.

**Attachment lifecycle**
1. As a non-viewer role, drag a file onto the upload area (or use "Choose file"); confirm
   filename, size, and live progress are shown.
2. Confirm an SVG file and a file over 10 MB are both rejected client-side before any request is
   sent.
3. Confirm a failed upload offers "Retry", and that retry starts a completely new upload rather
   than resubmitting the failed one.
4. Once uploaded, confirm the attachment appears in the persisted list with filename, type, size,
   uploader, timestamp, and scan status.
5. Download it and confirm the saved filename matches the original.
6. Remove it (with confirmation) and confirm it disappears from the list immediately.
7. As a viewer, confirm attachments can be downloaded but no upload control is shown.
8. Archive the bug; confirm uploads are disabled with an explanation, while existing attachments
   remain visible and downloadable.

**Notification lifecycle**
1. Trigger a mention, assignment, comment, status change, and reopen as different actors.
2. Confirm the recipient's bell unread count updates and the notifications list reflects each
   event with the correct label.
3. Mark one notification read individually, then use "Mark all read"; confirm the unread count
   updates accordingly.
4. Toggle an email preference off at `/notifications/preferences` and confirm no further email is
   queued for that event type.

**Role-permission checks**
1. Repeat the comment and attachment lifecycles above as developer, QA, reporter, and viewer,
   confirming the role matrix above holds in the UI.
2. Attempt a moderation action (redact/remove-any) as a non-administrator and confirm it is not
   offered in the UI.

**Archive behavior**
1. Confirm an archived bug blocks new comments/attachments with a visible explanation, while
   reads (comments, attachment downloads, activity) remain fully available.
2. Confirm administrator moderation (comment redact/delete-any, attachment remove-any) continues
   to work on an archived bug/project.

**Optimistic concurrency test**
1. Open the same bug in two browser tabs signed in as the same (or different) mutation-capable
   user.
2. Edit and save in tab A.
3. Edit and save in tab B without reloading; confirm a version-conflict message appears rather
   than a silent overwrite, and that "Reload latest version" recovers tab B.

**Accessibility**

This is a concise manual checklist, not a WCAG conformance claim — `npx playwright test
e2e/accessibility.spec.ts` covers automated axe-core scanning (serious/critical violations
only, no rules disabled) and `e2e/keyboard-navigation.spec.ts` covers a handful of
keyboard-only journeys; both should stay green. The items below are what a human still needs
to check by hand.

1. **Keyboard-only pass:** unplug your mouse (or just don't touch it) and complete the sign-in
   → dashboard → create a bug → comment with a mention → upload an attachment → archive a bug
   flow using only Tab, Shift+Tab, Enter, Space, arrow keys, and Escape. Confirm every
   interactive element is reachable and operable, and that focus never becomes visually
   invisible or gets trapped somewhere with no way out. *(Automated coverage exists for 5 of
   these sub-flows — sign-in, skip link, bug creation, notification dropdown, destructive-dialog
   cancel — in `e2e/keyboard-navigation.spec.ts`; comment editing, mentioning, and attachment
   upload specifically still need a live human pass.)*
2. **Skip link:** on any authenticated page, press Tab once (past the browser chrome, and past
   Next's dev-tools overlay if running the dev server — neither exists for a real user) and
   confirm "Skip to main content" appears and, on Enter, moves focus into the page's main
   content.
3. **Screen reader spot check:** with VoiceOver (macOS), NVDA, or JAWS, sign in, open a bug,
   post a mentioned comment, and confirm: the mention suggestion count is announced, the
   dialog's title/description are announced when a delete/archive confirmation opens, and
   upload progress doesn't spam a percentage announcement on every tick. **Not yet performed —
   no screen reader is available in this project's own sandbox/CI environment; this needs a
   human with real AT access before it can be marked done.**
4. **200% browser zoom:** zoom the whole page to 200% (not just text) on the dashboard, bugs
   list, and bug detail pages. Confirm no essential content or control disappears, and that any
   horizontal scrolling is contained to a specific wide element (a table, a chart) rather than
   the whole page. *(Verified via a simulated 640×480 viewport + `scrollWidth` check: 0px
   horizontal overflow on dashboard/bugs/bug-detail. A real browser's 200%-zoom reflow can still
   differ in ways a viewport-size proxy doesn't catch — worth a spot check in a real browser.)*
5. **Narrow viewport (~375px):** confirm the nav, forms, tables, and dialogs remain usable —
   wrapping rather than clipping content — down to a typical phone width. *(Verified concretely
   at 375×667: this caught a real bug — `VisuallyHiddenTable`'s `sr-only` `<table>` was
   contributing ~250px of real (if invisible) width, causing 19px of horizontal page overflow on
   the dashboard specifically. Fixed by moving `sr-only` onto a wrapping `<div>` instead; 0px
   overflow confirmed afterward. The new-bug form was already clean at this width.)*
6. **Reduced motion:** enable "reduce motion" in your OS accessibility settings, reload, and
   confirm loading skeletons and other animated states no longer pulse/animate (see the
   `prefers-reduced-motion` rule in `frontend/src/app/globals.css`). *(Verified via
   `page.emulateMedia({ reducedMotion: "reduce" })`: `animation-duration` and
   `transition-duration` both collapse to `0.01ms` as intended.)*
7. **Dialogs:** open each destructive confirmation (comment delete/redact, attachment remove,
   bug/project archive). Confirm: initial focus lands on Cancel (never the destructive button),
   Tab cycles only between the dialog's own Cancel/Confirm buttons, Escape closes it, and focus
   returns to the button that opened it.
8. **Forms:** submit each form (sign-in, setup, bug/project create, tag add) with invalid or
   empty required fields and confirm the error text is visually associated with its field (not
   just floating nearby) and is not conveyed by color alone.
9. **Charts:** confirm every dashboard chart has a visible heading and that its data is also
   available as a table in the accessibility tree (browser dev tools' Accessibility panel, or a
   screen reader) — not just visually, in the chart itself.
10. **Notification menu:** open the bell dropdown with Enter, confirm the unread count is
    announced as part of the trigger's accessible name (not conveyed by the red badge alone),
    and confirm Escape closes it and returns focus to the bell.

## Troubleshooting

**Container status**
```bash
docker compose ps
```
All services should show `Up`/`healthy`.

**Backend logs**
```bash
docker compose logs -f backend
```

**Find every log line for one failing request** — read `X-Request-ID` from the response
(browser DevTools → Network → Response Headers), then:
```bash
docker compose logs backend | grep '<request-id>'
```
See `docs/OBSERVABILITY.md` for the full request-correlation reference (log format, Celery task
correlation, sensitive-data policy).

**Frontend logs**
```bash
docker compose logs -f frontend
```

**Celery logs** (notification emails, attachment cleanup)
```bash
docker compose logs -f celery_worker
```

**PostgreSQL readiness**
```bash
docker compose exec db pg_isready -U ${POSTGRES_USER:-quorfix}
```

**Redis readiness**
```bash
docker compose exec redis redis-cli ping
```
Expect `PONG`.

**Migration checks**
```bash
docker compose exec backend python manage.py showmigrations
docker compose exec backend python manage.py migrate --check
```

**`seed_demo` refuses to run ("a different organization already exists")**
Community allows only one active organization. This means the database already has one from an
earlier `/setup` run or a previous seed with a different configuration. Use the reset procedure
above if you want a clean demo dataset — this discards all local data, so only do this locally.

**Clearing only disposable local data**
The reset procedure (`docker compose down -v`) removes the Postgres volume entirely. There is no
"partial" reset — Community's single-organization model means a clean demo dataset requires
starting from an empty database. Do not attempt to hand-edit rows to work around this.

**File-storage path**
Local attachments are written under `ATTACHMENTS_LOCAL_ROOT` (default: `backend/media`, see
`backend/config/settings/base.py`). Inside the `backend` container this is `/app/media`.

**Missing attachment file behavior**
If an attachment's database row says `uploaded` but the underlying file is missing from disk (e.g.
the volume was reset without also flushing the database), download returns a 404 and the backend
logs an error — the frontend shows "This file is no longer available." rather than a raw error.
This should not happen in normal operation; it indicates the storage volume and database have
gone out of sync.
