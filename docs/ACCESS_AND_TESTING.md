# Access and Manual Testing Guide

> Update this document whenever a phase changes routes, credentials, roles, setup commands, demo data, or available functionality.

This is the permanent reference for logging into a local Bug Fixer instance and manually
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
| Backend API docs (OpenAPI/Swagger) | http://localhost:8000/api/docs/ |
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

`seed_demo` is idempotent (safe to re-run) and refuses to run under production settings.

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

## Demo login accounts

Produced by `python manage.py seed_demo` (`backend/apps/core/management/commands/seed_demo.py`).
**Development-only accounts — never reuse these credentials anywhere but a local development
environment, and they are never seeded or exposed in production** (the command refuses to run
under production settings).

| Role | Email | Password |
| --- | --- | --- |
| Administrator | admin@bugfixer.local | BugFixerDemo2026! |
| Developer | developer@bugfixer.local | DeveloperDemo2026! |
| QA | qa@bugfixer.local | QADemo2026! |
| Reporter | reporter@bugfixer.local | ReporterDemo2026! |
| Viewer | viewer@bugfixer.local | ViewerDemo2026! |

`seed_demo` also creates three projects (`BFW`, `MOB`, `API`) with 24 demo bugs spread across
every status, priority, and severity, backdated across roughly the previous 45 days so the
dashboard (see below) has a meaningful trend to chart — and prints these credentials to the
console on each run (development settings only).

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
docker compose exec db pg_isready -U ${POSTGRES_USER:-bugfixer}
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
