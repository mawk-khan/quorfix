# Upgrading

Upgrade, migration, and rollback procedure for Quorfix Community's production Compose
stack (`docker-compose.prod.yml`). This document assumes you have already read
[docs/BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md) — it links to that runbook rather than
repeating it.

## 1. Scope and support policy

This is a conservative, pre-1.0 policy. It will get less conservative as the project
stabilizes; nothing below should be read as a permanent constraint.

- **Supported upgrade path: one released minor version at a time.** Upgrade `0.4.x → 0.5.x
  → 0.6.x`, not `0.4.x → 0.6.x` directly. Skipping minor versions is not guaranteed to work
  before 1.0 — intermediate migrations may assume intermediate application behavior that a
  skipped version never ran.
- **Patch upgrades within the same minor are supported directly** (`0.5.1 → 0.5.4` in one
  step) — patch releases don't change the migration graph.
- **Database backup and attachment backup are mandatory before every upgrade**, no exceptions
  — see step 5 below and [docs/BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md).
- **The backend and Celery worker must run the same image tag/digest.** They share the same
  Django app and task definitions; running them at different versions is unsupported.
- **Rolling, mixed-version deployment is not guaranteed before 1.0.** This stack's
  `docker-compose.prod.yml` topology doesn't support it anyway (a single `backend`/
  `celery_worker` container each) — this policy just makes explicit that mixed-version
  operation is never a deliberately supported state, not only that this topology can't do it.
- **Downgrade by code rollback alone is not guaranteed once migrations have run.** Some
  migrations are schema-reversible (see [Inspect current migration
  history](#inspect-current-migration-history) below) and some are not — treat all of them as
  one-way unless you have specifically verified otherwise for the migrations in question.
- **Backup restore is the default rollback mechanism** whenever migration reversibility is
  uncertain — which, per the audit below, is effectively always for now. See [Rollback
  decision tree](#14-rollback-decision-tree).
- **This document does not promise zero-downtime upgrades.** `docker-compose.prod.yml` has no
  second backend instance to fail over to — applying migrations means stopping `backend` and
  `celery_worker` for the duration (see [Database migration
  locking](#database-migration-locking)).

## Inspect current migration history

Audited against every migration under `backend/apps/*/migrations/` as of this writing
(34 applied migrations total; `apps.core` and `apps.analytics` have no models and no
migrations).

**Leaf nodes** (the newest migration per app):

| App | Leaf migration |
| --- | --- |
| accounts | `0002_user_email_unique` |
| organizations | `0002_seed_setup_lock` |
| projects | `0002_project_next_bug_number` |
| bugs | `0002_bug_bugs_bug_organiz_beeac0_idx` |
| comments | `0001_initial` |
| attachments | `0001_initial` |
| activities | `0005_bugactivity_activities__organiz_069dbe_idx` |
| notifications | `0001_initial` |

Plus Django/DRF built-ins: `admin`, `auth`, `contenttypes`, `sessions` at their own latest
migrations.

**RunPython usage:** exactly one — `organizations/migrations/0002_seed_setup_lock.py`. It has
a reverse function (`noop_reverse`), so Django will not raise `IrreversibleError` if you
migrate backward past it. **But the reverse is a no-op**: it does not delete the `SetupLock`
row the forward function seeds. Reversing this migration leaves the seeded row in place —
harmless (the row is a singleton lock, not user data), but do not describe this migration as
"data-reversible." It is schema/state-reversible only.

**Field removal or rename:** none. No `RemoveField`, `RenameField`, or `RenameModel` appears
anywhere in the current migration history.

**Irreversible data transformation:** none beyond the RunPython case above — there is no
migration that transforms or backfills existing data in a way that discards information.

**Migrations requiring application/worker coordination:** none of the current migrations
change a field/table shape that the application code depends on in an order-sensitive way
(no split of one column into two, no change of a column's meaning mid-migration). Ordinary
"stop app, migrate, restart app" (this document's procedure) is sufficient.

**Lock / table-rewrite risk** — the operations below run `CREATE INDEX`/`ADD CONSTRAINT`
without `CONCURRENTLY` (Django's `AddIndex`/`AddConstraint` don't use it by default), so each
takes a table lock for the duration of the index/constraint build:

| Migration | Table | Operation |
| --- | --- | --- |
| `accounts/0002_user_email_unique` | `accounts_user` | Adds a unique constraint on `Lower(email)` — requires a full table scan to validate uniqueness |
| `bugs/0002_bug_bugs_bug_organiz_beeac0_idx` | `bugs_bug` | Adds an index on `(organization, resolved_at)` |
| `activities/0005_bugactivity_...` | `activities_bugactivity` | Adds an index on `(organization, -created_at)` |

All three of these have **already been applied** in the current codebase's migration
history — they are not pending for an upgrade *from* this codebase, only relevant if you are
upgrading from a version old enough to not have them yet. They're documented here so the
pattern (and the tables it applies to — `bugs`, `activities`, and by extension `comments`,
`notifications`, and `attachments`, the largest tables in this schema) is understood for
*future* migrations, not just these specific ones. See [Database migration
locking](#database-migration-locking).

Every `0001_initial` migration's own `AddIndex`/`AddConstraint` operations run against a
brand-new, empty table at install time — no lock risk there; the risk above only applies to
an index/constraint added to a table that may already hold rows, which is what an *upgrade*
(as opposed to a first install) actually does.

## 2. Before upgrading

- Confirm the production stack is currently healthy (`make prod-check`, `docker compose -f
  docker-compose.prod.yml ps`).
- Make sure you have a maintenance window — see [Database migration
  locking](#database-migration-locking). This is not a zero-downtime procedure.
- Make sure the target version's release notes have been read (step 3) and its migrations
  reviewed (step 9) *before* you stop anything.

## 3. Read release notes

Read the target release's changelog/release notes in full before upgrading, specifically for:

- New required environment variables (check them against `.env.example` for the target
  version).
- Any migration flagged there as long-running or requiring a maintenance window.
- Any breaking API or Celery task signature change (see [Worker/application
  compatibility](#workerapplication-compatibility)).

## 4. Confirm current version

```bash
# Git SHA and image labels of what's currently deployed (see "Version metadata" below):
scripts/inspect_version.sh
# or:
make prod-version
```

If the running containers were built with `VERSION=<something other than "local">`, pass it
explicitly: `scripts/inspect_version.sh <that value>` (or `VERSION=<value> make prod-version`).

## 5. Create coordinated backup

**Mandatory, every upgrade, no exceptions.** Full procedure:
[docs/BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md).

```bash
make backup DEST=/path/outside/repo
```

Do not proceed until this reports `status=complete` in its manifest.

## 6. Validate the target release

```bash
# Fetch/checkout the target release's code first, then, still on the CURRENT running
# containers (nothing stopped yet):
docker compose -f docker-compose.prod.yml --env-file .env config >/dev/null && echo "config OK"
```

If this fails, stop — do not proceed to building/deploying the target images.

## 7. Pull/build target images

```bash
make prod-build
# or, if pulling from a registry instead of building locally, tag/pull the target
# VERSION so docker-compose.prod.yml's quorfix-backend:${VERSION:-local} /
# quorfix-frontend:${VERSION:-local} resolve to the target images.
```

Confirm what you actually built/pulled before going further:

```bash
make prod-version
```

## 8. Stop write traffic

```bash
docker compose -f docker-compose.prod.yml --env-file .env stop backend celery_worker
```

`db`, `redis`, and `frontend` stay up — `frontend` will simply show connection errors for
`/api/*` requests until `backend` is back (its own healthcheck is independent of `backend`'s,
by design — see `docker-compose.prod.yml`'s comment on the `frontend` service, from Chunk C).

## 9. Check migration plan

```bash
make prod-migrations-check   # nonzero if any model change has no migration file (drift)
make prod-migrations-plan    # prints the full plan; always exits 0 — read the output
```

Review the plan's newly-added (`[ ]`) entries against [Database migration
locking](#database-migration-locking) — if any of them touch `bugs`, `activities`,
`comments`, `notifications`, or `attachments` with an index/constraint addition, budget
maintenance-window time accordingly.

## 10. Apply migrations

```bash
make prod-migrate
```

Never run this automatically as part of `prod-up` or any other non-interactive step — it is
always this explicit, separate command, run by an operator who has already completed steps
5–9.

## 11. Restart backend and Celery worker

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d backend celery_worker
```

## 12. Run post-upgrade smoke tests

```bash
make upgrade-smoke
```

Runs `scripts/upgrade_smoke.sh`: Compose config, backend liveness, backend readiness,
frontend response, no unapplied migrations, and that the `celery_worker` container is
running. All read-only — see [Upgrade smoke script](#upgrade-smoke-script) below for exactly
what it does and does not prove.

## 13. Verify attachments and notifications

`scripts/upgrade_smoke.sh` deliberately stops short of this — it proves the containers are
alive, not that a real notification is actually delivered end to end. Do this manually,
signed in as a real account (not a demo account, unless the environment genuinely is a demo
environment):

- [ ] Download a known, pre-upgrade attachment and confirm it opens correctly.
- [ ] Trigger a real event (assign a bug, post a comment that mentions someone) and confirm
      the recipient's notification actually appears — this is the only way to prove
      `celery_worker` is genuinely consuming from the broker, not just that its container is
      "running."

(This is the same checklist as [docs/BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md)'s
post-restore verification — an upgrade and a restore both end with "prove the app actually
works," not just "the process started.")

## 14. Rollback decision tree

Work through this **in order** — the first branch that applies to your situation is the one
to follow.

### Before migrations were applied

The new image failed to start, failed its healthcheck, or failed smoke testing — and you
never ran `make prod-migrate` against it.

```bash
docker compose -f docker-compose.prod.yml --env-file .env stop backend celery_worker
# Re-point VERSION (or your registry tag) back to the previous image, then:
docker compose -f docker-compose.prod.yml --env-file .env up -d backend celery_worker
```

**No database restore is required** — nothing about the database changed.

### After migrations that are verified reversible

Only take this path if you have **actually tested** `manage.py migrate <app>
<previous_migration_name>` for the specific migrations involved — per the audit above, that
is essentially none of the current migration set today (see "RunPython usage" — the one
`RunPython` migration's reverse is a no-op, and no migration in this codebase has been through
a reversal drill). If you have verified it for a *future* migration:

```bash
docker compose -f docker-compose.prod.yml --env-file .env stop backend celery_worker
docker compose -f docker-compose.prod.yml --env-file .env run --rm backend \
  python manage.py migrate <app_label> <previous_migration_name>
# Re-point VERSION back to the previous image:
docker compose -f docker-compose.prod.yml --env-file .env up -d backend celery_worker
```

Then run the same smoke/verification steps as a forward upgrade (steps 12–13).

### After uncertain or irreversible migrations (the default assumption)

This is the path for essentially every migration in the current codebase, per the audit
above.

```bash
docker compose -f docker-compose.prod.yml --env-file .env stop backend celery_worker
scripts/restore_db.sh --confirm-restore /path/to/pre-upgrade-backup/database.dump
scripts/restore_attachments.sh --confirm-restore /path/to/pre-upgrade-backup/attachments.tar.gz
# Re-point VERSION back to the previous image, then:
docker compose -f docker-compose.prod.yml --env-file .env up -d backend celery_worker
make upgrade-smoke
```

(`scripts/restore_db.sh` and `scripts/restore_attachments.sh` already stop/restart
`backend`/`celery_worker` themselves — see
[docs/BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md) — the explicit `stop` above is only to
make the ordering unambiguous if you're running these steps interactively one at a time.)

### After new writes happened under the upgraded version

**Restoring the pre-upgrade backup discards every write made after that backup was taken —
including anything created between finishing the upgrade and discovering the problem.** This
is not a hidden trade-off: if the upgraded version has been accepting real user traffic for
any length of time before you decide to roll back, restoring the pre-upgrade backup means
those bugs, comments, attachments, and notifications are gone. There is no partial/selective
restore tooling in this chunk. If that data loss is unacceptable, the only alternative is
fixing forward on the upgraded version rather than rolling back — weigh that against the
severity of whatever prompted the rollback consideration.

## 15. Restore-from-backup procedure

This is exactly [docs/BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md)'s "Full restore
procedure" — see the rollback decision tree above for when to use it in an upgrade context;
see that document for the procedure itself. Not duplicated here.

## 16. Troubleshooting

**`make prod-migrations-check` fails**
There are model changes with no migration file. Do not proceed with the upgrade using this
code — the target release is missing a migration it needs. This points at a problem in the
target release itself, not your environment.

**`make prod-upgrade-check` (or `prod-migrations-check`/`migrate --check` individually) fails
with unapplied migrations before you've even started**
Someone deployed code without running `make prod-migrate` on a previous upgrade. Investigate
before proceeding — you may be further behind than you think.

**Migration takes far longer than expected**
Check `docker compose -f docker-compose.prod.yml exec db psql -U <user> -d <db> -c "SELECT
pid, state, query, now() - query_start AS duration FROM pg_stat_activity WHERE state !=
'idle';"` in another terminal — a long-running migration on a large table (see [Database
migration locking](#database-migration-locking)) is expected to hold a lock, not necessarily
stuck. If it genuinely appears stuck (no progress, no lock waits resolving), do not `Ctrl-C`
a migration mid-run without a clear plan — an interrupted `ALTER TABLE`/`CREATE INDEX` can
leave the schema in a partially-migrated state. See [Rollback decision
tree](#14-rollback-decision-tree).

**Backend won't become healthy after restart**
`make upgrade-smoke` output shows which specific check failed. If it's readiness specifically,
`docker compose -f docker-compose.prod.yml --env-file .env logs backend` almost always shows
the actual exception (database, cache, or attachment-storage connectivity — see
`apps.core.views.ReadinessCheckView`).

**Celery worker container is running but tasks aren't processing**
`scripts/upgrade_smoke.sh` only proves the *container* is running — see [Verify attachments
and notifications](#13-verify-attachments-and-notifications) for the real, task-level check.
`docker compose -f docker-compose.prod.yml --env-file .env logs celery_worker` is the next
step if that manual check fails.

## 17. Version-specific notes

This section exists for upgrade notes specific to a particular version transition (e.g. a
migration that needs an unusually long maintenance window, or a required new environment
variable). Two entries exist so far, both found by actually running the disposable upgrade
drill (see below) against a pre-Chunk-C commit rather than by inspection alone — recorded here
as the template for what a real entry looks like, since no tagged release exists yet to attach
them to formally:

**Upgrading across the introduction of `docker-compose.prod.yml` (Phase 6 Chunk C) to a
version before it:**

- **The pre-Chunk-C backend image hardcodes `SECURE_SSL_REDIRECT = True`** with no environment
  override — every plain-HTTP request, including internal liveness/readiness checks, gets
  redirected to HTTPS and fails (there is no TLS inside the Docker network). Chunk C added
  `DJANGO_SECURE_SSL_REDIRECT` specifically to fix this for the `backend`/`celery_worker`
  services' internal traffic. A pre-Chunk-C image cannot be health-checked over plain HTTP at
  all — this is expected, not a bug in the drill infrastructure, and is exactly why that
  environment variable exists.
- **The pre-Chunk-C backend image has no non-root runtime user** — it runs as root. Chunk C's
  image introduced a non-root `app` user (uid 1000) and a dedicated, pre-chowned
  `/data/attachments` path. Upgrading an attachments volume that was ever written to by a
  pre-Chunk-C (root) container into a Chunk-C-or-later (non-root) container requires a
  one-time ownership fix — e.g. `docker run --rm -v <attachments_data_volume>:/data/attachments
  busybox chown -R 1000:1000 /data/attachments` — before the new image can start successfully;
  otherwise `check_attachment_storage` (run by `entrypoint.sh` on every container start) fails
  with "Permission denied" and the container never comes up. This only applies to that specific
  version boundary, not to any upgrade between two already-non-root versions.

None of Quorfix Community's actual migrations have changed between any released version yet
(no version transition has shipped) — this section will grow as real releases happen.

---

## Version metadata

`backend/Dockerfile` and `frontend/Dockerfile` (Chunk C) both accept `VERSION`/`VCS_REF`
build args and set them as OCI labels (`org.opencontainers.image.version`,
`org.opencontainers.image.revision`, `org.opencontainers.image.source`) on the built image.
`scripts/inspect_version.sh` (`make prod-version`) reads them back:

```bash
scripts/inspect_version.sh          # inspects quorfix-{backend,frontend}:${VERSION:-local}
scripts/inspect_version.sh 1.2.3    # inspects a specific tag
```

If an image was built without passing `VERSION`/`VCS_REF` (the default for an ordinary local
`make prod-build`, where both default to `local`/`unknown`), the labels are empty — the script
reports this explicitly rather than printing a blank line, and exits nonzero only if the image
itself can't be found at all (missing labels on a found image are reported but don't fail the
command, since "built without version metadata" is a valid, if less useful, state to inspect).

There is no HTTP version endpoint. The application does not expose one, and this chunk does
not add one — image labels plus `git rev-parse HEAD` against the deployed checkout (also
recorded in every `scripts/backup.sh` manifest's `git_sha` field — see
[docs/BACKUP_AND_RESTORE.md](./BACKUP_AND_RESTORE.md)) are sufficient for this stack's actual
operational needs, and a public version endpoint would expose internal repository/dependency
metadata to anyone who can reach the API for no corresponding operational benefit.

## Worker/application compatibility

- **The backend and Celery worker must run the same image tag/digest** — `docker-compose.prod.yml`
  builds both from the same `backend/Dockerfile`, so this only breaks if you manually
  override one service's image independently of the other. Don't.
- **Stop both before applying migrations, restart both after** — see steps 8–11 above. A
  worker left running against a database mid-migration can observe a schema in a transitional
  state.
- **Queued tasks may contain payloads from the previous application version.** Every task in
  this codebase is inspected below.

**Task signature audit** (`grep -rn "@shared_task"` across `backend/apps/`):

| Task | Payload shape |
| --- | --- |
| `apps.notifications.tasks.create_notifications_for_event` | Keyword-only: `event_type` (a plain string — Django `TextChoices` members serialize to their string value), `organization_id`, `bug_id`, `actor_id=None`, `activity_id=None`, `comment_id=None`, `assignee_id=None`. Re-resolves every ID from the database inside the task — never trusts a value carried across the broker beyond the ID itself. |
| `apps.notifications.tasks.send_notification_email` | One positional arg: `notification_id` (a UUID string). Re-fetches the `Notification` row itself. |
| `apps.attachments.tasks.delete_attachment_object` | One positional arg: `storage_key` (a plain string). |

**No task anywhere serializes a Django model instance or any non-JSON-primitive payload** —
`CELERY_TASK_SERIALIZER = "json"` / `CELERY_ACCEPT_CONTENT = ["json"]`
(`backend/config/settings/base.py`) makes this structural, not just a coding convention: it is
not possible to accidentally queue a pickled model object with this configuration. This is
what the "stable IDs rather than serialized model objects" pattern buys: a queued task from
the previous version's code and a worker running the next version's code exchange nothing
more than plain JSON scalars, and the newer code re-derives everything else from the database
at execution time — a genuinely narrow surface for cross-version incompatibility.

**The actual remaining risk, found by inspection, not currently present:** if a *future*
change adds a new required (non-default) keyword argument to any of these tasks, a task queued
before the upgrade (using the old call signature) and executed after the upgrade (by the new
worker code) would raise `TypeError` on missing argument. Every optional argument in the
current signatures already defaults to `None`, which is what avoids this today. **Nothing in
the current codebase has this problem** — this is documented so it isn't introduced by
accident later, not because a fix is needed now. Per this chunk's scope, no queue-drain
mechanism is added, because no real incompatibility exists to drain for.

`create_notifications_for_event`'s `_resolve_recipients` dispatch also already degrades
gracefully for an unrecognized `event_type` (falls through to `return []`, not an exception) —
worth noting as a second, independent reason a hypothetical future event-type rename wouldn't
crash an in-flight queued task, only silently produce no notifications for it.

## Database migration locking

- Schema migrations that add an index or constraint to an **existing, populated** table (see
  the audit's lock-risk table above) take a table lock for the duration of the index/constraint
  build — `Django`'s `AddIndex`/`AddConstraint` operations do not use
  `CREATE INDEX CONCURRENTLY` by default, and none of the current migrations override that.
- **Duration depends on dataset size and PostgreSQL's own behavior** for the specific
  operation — this document makes no claim about exact timing. Larger tables take longer;
  that is the only claim made here.
- **Schedule a maintenance window for every upgrade that includes a schema migration** — which
  is effectively every upgrade, since `backend`/`celery_worker` are stopped for the whole
  migration step regardless (step 8) in this topology.
- **Review the migration plan before applying it** (step 9) — know what's about to run before
  you run it, not after.
- **The largest tables in this schema** — and therefore the ones most likely to make a future
  index/constraint-adding migration take real time — are `bugs`, `activities`, `comments`,
  `notifications`, and `attachments`' metadata table. Any future migration touching one of
  these deserves specific attention in that release's [Version-specific
  notes](#17-version-specific-notes).

## Upgrade smoke script

`scripts/upgrade_smoke.sh` (`make upgrade-smoke`) — see the script's own header comment for
the full list of what it checks. It is intentionally narrow:

- It **does** prove: the Compose config resolves, backend liveness and readiness both
  respond, the frontend responds, there are no unapplied migrations, and the `celery_worker`
  container is in the `running` state.
- It **does not** prove: that Celery is actually consuming and completing tasks (only that its
  container is running — a stuck or crash-looping-but-restarting worker can still show
  "running"), that notification email delivery works, or anything requiring a signed-in
  session. Those need the manual checklist in [Verify attachments and
  notifications](#13-verify-attachments-and-notifications), which requires real credentials
  this script deliberately does not touch.
- It creates, deletes, and modifies nothing — every check is a read-only HTTP request or a
  read-only Django management command (`migrate --check` never applies anything).
