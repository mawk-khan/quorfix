# Backup and Restore

Backup and restore procedures for Quorfix Community's production Compose stack
(`docker-compose.prod.yml`): PostgreSQL, local attachment storage, and a full
Community recovery. Scripts referenced below live in `scripts/`.

**Read this before taking or restoring a backup:**

- **PostgreSQL and attachments must be backed up together.** They are one
  coordinated recovery set, not two independent backups.
- **A database-only restore may leave attachment records pointing to missing
  files.** Bug and comment records reference attachment rows, which reference
  files on the attachments volume — restoring the database alone can leave
  "phantom" attachments that 404 on download.
- **A media-only restore may create unreferenced files.** Restoring the
  attachments volume alone, against a database that doesn't know about those
  files (or has moved on since), leaves orphaned files nothing points to.
- **Redis is not the system of record and is not part of the required
  recovery set.** It backs the shared cache and the Celery broker only — see
  [Scope and assumptions](#1-scope-and-assumptions).
- **Test restores regularly. An untested backup is not a verified recovery
  plan.** The only way to know a backup actually restores is to restore it —
  see [the disposable restore drill](#8-full-restore-procedure) this
  procedure is written to support.

## 1. Scope and assumptions

This document covers `docker-compose.prod.yml`'s topology specifically — the
`db`, `redis`, `backend`, `celery_worker`, and `frontend` services, as
committed to this repository. It does not cover a different production
topology; if you operate Quorfix some other way (managed PostgreSQL, a
different orchestrator), adapt the underlying commands, not the concepts.

Relevant facts from `docker-compose.prod.yml`, used throughout:

| Fact | Value |
| --- | --- |
| Database service name | `db` |
| Database name/user env vars | `POSTGRES_DB`, `POSTGRES_USER` (password: `POSTGRES_PASSWORD`, never read by these scripts — see [PostgreSQL backup](#4-postgresql-backup)) |
| PostgreSQL named volume | `postgres_data`, mounted at `/var/lib/postgresql/data` in `db` |
| Attachment named volume | `attachments_data`, mounted at `/data/attachments` in both `backend` and `celery_worker` |
| `ATTACHMENTS_LOCAL_ROOT` | `/data/attachments` (backend and worker) |
| Backend service name | `backend` |
| Worker service name | `celery_worker` |
| Stop write traffic without deleting data | `docker compose -f docker-compose.prod.yml stop backend celery_worker` (keeps `db`/`redis` running, keeps volumes) |
| `db` / `redis` host ports | **None.** Neither service publishes a host port — only `frontend` does. Backup/restore always run through Compose (`exec`/`run`), never a direct host connection. |

**Redis is out of scope for the required recovery set.** It holds the Celery
broker/result backend and the short-TTL analytics dashboard cache — genuinely
disposable operational state, not application data. Losing it loses
in-flight Celery tasks and forces a cache rebuild on next read; it never
loses anything a user created. `docker-compose.prod.yml`'s `redis_data`
volume (RDB snapshotting) exists to smooth over routine container
restarts, not as a backup target.

**Migrations are schema, not data** — they ship with the application code
(`backend/apps/*/migrations/`) and are version-controlled. They are not part
of the backup; see [Full restore procedure](#8-full-restore-procedure) for
how they're re-applied after a database restore.

**`.env` is never included in a backup.** It contains `DJANGO_SECRET_KEY`,
`POSTGRES_PASSWORD`, and other secrets — see
[Security and operational constraints](#11-retention-and-encryption-guidance).

## 2. Recovery-set concept

A **recovery set** is one directory produced by `scripts/backup.sh`,
containing everything needed to restore Quorfix Community to a single
point in time:

```
quorfix-backup-YYYYmmddTHHMMSSZ/
  manifest.txt          # what this recovery set is, and whether it's complete
  database.dump          # pg_dump --format=custom (schema + data + migration records)
  attachments.tar.gz     # tar.gz of the attachments_data volume's contents
  checksums.sha256       # sha256sums of database.dump and attachments.tar.gz
```

Treat the directory as a unit: copy it, retain it, and restore from it as one
thing, not as four independent files that happen to share a timestamp.
`manifest.txt`'s `status=complete` line is the only trustworthy signal that
every step of the backup actually succeeded — see
[Backup verification](#6-backup-verification).

### Naming compatibility

`quorfix-backup-` is the directory prefix new backups are created with,
following the Phase 6 Chunk K product rename. It is **only a naming
convention for new backups** — `restore_db.sh`/`restore_attachments.sh` take
a direct path to `database.dump`/`attachments.tar.gz` and never inspect or
require any particular parent-directory name; the only thing they validate
is `manifest.txt`'s `format_version` field (see [Backup
verification](#6-backup-verification)). A recovery set created before the
rename, named `bugfixer-backup-YYYYmmddTHHMMSSZ/`, restores exactly the same
way — nothing to convert, rename, or migrate. `format_version` (currently
`1`) is the actual compatibility contract; the directory name has never been
part of it. See `scripts/tests/test_backup_restore_guards.sh`'s legacy-prefix
case for the automated proof.

## 3. Before taking a backup

- Make sure the production stack is up (`db` and `redis` healthy at minimum;
  `backend` running is needed for the manifest's migration summary, but the
  backup itself does not require it — see [PostgreSQL
  backup](#4-postgresql-backup)).
- Decide on a backup destination **outside this repository** —
  `scripts/backup.sh` refuses to write inside the repo, and nothing here
  invents a default location. A sensible convention:
  `/var/backups/quorfix/` on the host, or a mounted volume dedicated to
  backups.
- Make sure there's enough free disk space at the destination.
  `scripts/backup.sh` prints a soft warning below 500MB free, but the actual
  requirement depends entirely on your database and attachment volume sizes
  — check `docker system df -v` or `du -sh` against the running volumes if
  you're unsure.
- **Ordinary backups do not stop application traffic**, and don't need to —
  `pg_dump` takes a consistent MVCC snapshot without blocking concurrent
  writers. See [Consistency limitations](#consistency-limitations) below for
  what this does and doesn't guarantee.

### Consistency limitations

`scripts/backup.sh` runs the database backup and the attachment backup as
two separate operations, a few seconds apart, against a stack that keeps
accepting writes the whole time. This is the right tradeoff for routine,
frequent backups — but it means:

- A file uploaded (or deleted) in the gap between the two steps may be
  recorded in one artifact and not the other.
- The two artifacts are **not** a byte-for-byte, transactionally
  synchronized snapshot of each other.

**A fully synchronized database + attachments snapshot requires a
maintenance window.** PostgreSQL's own consistency guarantees (MVCC) and a
plain filesystem `tar` cannot be made atomic together with the simple tools
used here — that would require either stopping `backend`/`celery_worker` for
the whole backup (routine backups deliberately don't do this — see
[Full restore procedure](#8-full-restore-procedure) for the destructive
counterpart, restore, which does stop them) or a storage layer with true
cross-volume snapshot support, which is out of scope for this cloud-neutral
setup. For routine operational backups this gap is an acceptable, documented
tradeoff; if you need a guaranteed-consistent snapshot (e.g. before a risky
migration), stop `backend` and `celery_worker` first
(`docker compose -f docker-compose.prod.yml stop backend celery_worker`),
run `scripts/backup.sh`, then restart them.

## 4. PostgreSQL backup

```bash
scripts/backup_db.sh [-f COMPOSE_FILE] [-e ENV_FILE] <output-file>
# or, as part of a coordinated backup:
make backup DEST=/path/outside/repo
```

- Format: `pg_dump --format=custom` (schema + data, including migration
  records) — **not** plain SQL. Custom format is what enables
  `pg_restore --list` verification, `--no-owner` restore, and selective
  restore if ever needed; a plain-SQL dump supports none of that.
- Compression: `--compress=6` (moderate zlib level, supported by every
  PostgreSQL version this stack targets).
- Runs `pg_dump`/`pg_restore` **from inside the running `db` container**
  (`docker compose exec db ...`), never a host-installed PostgreSQL client —
  the client version always matches the server exactly.
- **Never reads, needs, or prints `POSTGRES_PASSWORD`.** `docker compose
  exec` connects to PostgreSQL over the container's local Unix socket, which
  the official `postgres` image trusts locally by default
  (`POSTGRES_HOST_AUTH_METHOD` is not overridden in
  `docker-compose.prod.yml`) — only network connections require the
  password. `POSTGRES_USER`/`POSTGRES_DB` are read from the `db` container's
  own environment, not from the host.
- Writes through a `.tmp.$$` temporary file in the same directory as the
  output, verifies it with `pg_restore --list`, and only then atomically
  `mv`s it into place with `chmod 600`. Refuses to run at all if the output
  file already exists. The temporary file is removed on any failure.
- Does not stop `backend`/`celery_worker` — see
  [Consistency limitations](#consistency-limitations).

## 5. Attachment backup

```bash
scripts/backup_attachments.sh [-f COMPOSE_FILE] [-e ENV_FILE] <output-file>
# or, as part of a coordinated backup:
make backup DEST=/path/outside/repo
```

- Produces a gzip-compressed tar archive (`tar czf ... -C /data/attachments
  .`) of the `attachments_data` volume's contents, with paths recorded
  relative to the attachments root (e.g. `./org-id/bug-id/attachment-id.ext`
  — never as absolute paths).
- Runs via a disposable `docker compose run --rm --no-deps` invocation of
  the already-built `backend` image itself — no separate helper image is
  pulled, and the exact volume/path declared in `docker-compose.prod.yml` is
  reused as-is (no host-specific bind-mount path is assumed).
- The container's own `ENTRYPOINT` is bypassed for this step
  (`--entrypoint ""`), so a plain filesystem backup never depends on the
  full Django production system checks passing — those checks matter for
  serving traffic, not for reading files off a mounted volume.
- Handles an empty attachment volume successfully — `tar` still produces a
  small, valid, listable archive (just the root directory entry) for an
  installation with no uploads yet.
- Writes through a `.tmp.$$` temporary file, verifies it with `tar tzf`, and
  only then atomically renames it into place with `chmod 600`. Refuses to
  run if the output file already exists.

## 6. Backup verification

Every artifact is verified as part of producing it — this is not a separate
manual step, but here's what "verified" means for each:

- **`database.dump`**: `pg_restore --list` must be able to read the table of
  contents (run automatically by `scripts/backup_db.sh` before the temp file
  is renamed into place).
- **`attachments.tar.gz`**: `tar tzf` must be able to list the archive (run
  automatically by `scripts/backup_attachments.sh`).
- **`checksums.sha256`**: generated by `scripts/backup.sh` after both
  artifacts exist, covering `database.dump` and `attachments.tar.gz`
  (`sha256sum`/`shasum -a 256`), then immediately self-verified
  (`sha256sum -c`) before the manifest is marked complete.
- **`manifest.txt`**: `status=complete` is written **only** after every
  step above has succeeded — never before, never speculatively. If you ever
  see `status=in_progress` or `status=failed` in a manifest, the recovery
  set is incomplete; do not restore from it (`scripts/restore_db.sh` and
  `scripts/restore_attachments.sh` both refuse to, if a `manifest.txt` is
  present — see [Restore prerequisites](#7-restore-prerequisites)).

Before **restoring**, always re-verify independently of what the backup run
claimed, since the recovery set may have been copied, moved, or aged since
then:

```bash
cd /path/to/quorfix-backup-YYYYmmddTHHMMSSZ
sha256sum -c checksums.sha256
grep -E '^(status|format_version)=' manifest.txt
```

`scripts/restore_db.sh` and `scripts/restore_attachments.sh` both do this
automatically before touching anything — see
[Restore prerequisites](#7-restore-prerequisites) — but running it yourself
first is a cheap, non-destructive sanity check.

### Manifest fields

```
format_version=1
status=complete
timestamp_utc=20260806T120000Z
app_version=0.5.0
git_sha=4bcdbe835725ea40377415ad4888bf603643fcc0
compose_file=docker-compose.prod.yml
database_service=db
database_format=pg_dump-custom
attachment_volume=attachments_data
attachment_path_in_container=/data/attachments
attachment_format=tar.gz
migrations_summary=applied=34 unapplied=0
```

`app_version`/`git_sha` are best-effort: `app_version` is the `VERSION`
environment variable if set when `scripts/backup.sh` ran (the same one
`docker-compose.prod.yml` bakes into image labels), `unknown` otherwise.
`git_sha` is `git rev-parse HEAD` against this repository checkout,
`unknown` if `git` isn't available or this isn't a checkout.
`migrations_summary` is best-effort too (`unavailable` if `backend` wasn't
running to ask) — it is operator context, not something restore logic
parses or depends on.

## 7. Restore prerequisites

**Restores are destructive.** Read the whole procedure before running
anything.

- You need the full recovery-set directory (or at minimum, the specific
  artifact plus its `checksums.sha256` in the same directory —
  `scripts/restore_db.sh`/`scripts/restore_attachments.sh` each restore one
  artifact and only require that one plus the checksum file next to it, not
  the entire set).
- **Both restore scripts require `--confirm-restore` explicitly.** There is
  no interactive prompt to answer "yes" to — this is deliberate: a fixed
  literal flag behaves identically whether it's run from a terminal or from
  CI/a non-interactive shell, so there's no ambiguous prompt that could hang
  or be silently auto-answered.
- **Neither script discovers "the latest backup" automatically.** You always
  pass an explicit path. This is deliberate — the whole point of choosing a
  recovery set is a decision a human (or a change-controlled process) makes,
  not something a script infers.
- Both scripts validate before mutating anything:
  1. The input file exists and is non-empty.
  2. Its checksum matches the entry for it in `checksums.sha256` in the same
     directory (missing file, missing entry, or mismatch all refuse to
     proceed).
  3. If a `manifest.txt` is present in that directory, `format_version`
     matches what these scripts expect and `status=complete` — otherwise
     they refuse. (If no `manifest.txt` is present at all — e.g. you copied
     just the one artifact plus its checksum out of a recovery set — they
     proceed on the checksum check alone, with a warning.)
- Neither script prints credentials, and neither claims to reverse
  migrations — see [Full restore procedure](#8-full-restore-procedure).

## 8. Full restore procedure

This restores **both** the database and attachments — the coordinated
recovery set as a whole. Run the two scripts back to back from the same
recovery-set directory:

```bash
scripts/restore_db.sh --confirm-restore /path/to/quorfix-backup-.../database.dump
scripts/restore_attachments.sh --confirm-restore /path/to/quorfix-backup-.../attachments.tar.gz
```

(or `make restore-db-confirm IN=...` / `make restore-attachments-confirm
IN=...` — see the Makefile.)

### Database restore (`scripts/restore_db.sh`)

1. Validate the dump, checksum, and manifest (see
   [Restore prerequisites](#7-restore-prerequisites)).
2. Stop `backend` and `celery_worker` — `db` and `redis` keep running.
   **Never restore over a database receiving writes**; this step is what
   makes the rest of the procedure safe.
3. Terminate any remaining sessions on the target database
   (`pg_terminate_backend`, from a connection to the `postgres` maintenance
   database).
4. **Drop and recreate the target database** (`DROP DATABASE IF EXISTS` /
   `CREATE DATABASE ... OWNER ...`). This is the chosen restore strategy —
   deliberately not `pg_restore --clean --if-exists` into a pre-existing
   database. A freshly recreated database has no leftover objects the dump
   doesn't know about; `--clean` only drops objects the dump itself
   declares, which can't guarantee the same thing if the live database has
   drifted (e.g. a manually-created index or table).
5. `pg_restore` the dump into the fresh database (`--no-owner`, so restore
   doesn't depend on matching Postgres roles between backup-time and
   restore-time).
6. Run Django migrations (`manage.py migrate`, **forward only** — see
   [Failure and rollback guidance](#10-failure-and-rollback-guidance) for
   what this means if the dump predates a schema change already rolled out).
7. Restart `backend` and `celery_worker`.

### Attachment restore (`scripts/restore_attachments.sh`)

1. Validate the archive, checksum, and manifest.
2. Stop `backend` and `celery_worker` — they hold the attachments volume
   mounted.
3. Validate and extract the archive into a **staging directory inside the
   container** (`/tmp/attachments-restore-staging`) — nothing under the real
   `/data/attachments` is touched yet. Every archive member is validated
   before extraction (no absolute paths, no `..` traversal, no symlinks or
   special files — see [Path traversal protection](#path-traversal-protection)
   below); an unsafe or corrupt archive fails here, before anything real is
   deleted.
4. Only once staging succeeds: clear `/data/attachments` and copy the
   staged, validated files into place. **This replaces the volume's
   contents — it does not merge with what's already there.** A silent merge
   could leave old, unreferenced files in place that mask an incomplete
   restore (files present that shouldn't be, or files from a stale backup
   overwriting nothing because the restore never actually touched them).
   This script does not first snapshot the volume it's about to replace —
   if you want that safety net, run `scripts/backup.sh` against the current
   (soon-to-be-replaced) state first.
5. Restart `backend` and `celery_worker`.

### Path traversal protection

Backup archives are treated as untrusted input by the time they reach
restore. `backend/apps/core/tar_safety.py` (invoked via the
`extract_attachments_archive` management command, which
`restore_attachments.sh` calls) rejects, before extracting anything:

- Absolute paths (`/etc/passwd`).
- `..` traversal, whether leading (`../../etc/passwd`) or embedded
  (`subdir/../../etc/passwd`).
- Symlinks and hard links (a plain filesystem tar of the attachments root
  never legitimately contains one).
- Any tar entry that isn't a regular file or directory (device nodes, FIFOs,
  etc).

Validation happens as a first pass over every member before any extraction
starts — one unsafe member aborts the whole restore with nothing written to
disk, not a partial extraction up to the bad entry. On top of the explicit
checks, extraction itself also passes Python's `tarfile.extractall(...,
filter="data")` (PEP 706, Python 3.12+) as a second, independent layer of
defense. See `backend/apps/core/tests/test_tar_safety.py` for the test
coverage.

## 9. Post-restore verification

Run through this checklist after every restore, whether it's a real
incident or a drill. Do not use demo credentials (`seed_demo`) as a
production restore check — sign in as a real administrator account that
existed in the restored data, unless the restored database is explicitly a
demo/test environment.

**Automated / command-line:**

```bash
docker compose -f docker-compose.prod.yml --env-file .env run --rm backend python manage.py check
docker compose -f docker-compose.prod.yml --env-file .env run --rm backend python manage.py showmigrations --plan
docker compose -f docker-compose.prod.yml --env-file .env run --rm backend python manage.py migrate --check   # exits nonzero if anything is unapplied
curl -f http://localhost:3000/api/health/
curl -f http://localhost:3000/api/health/ready/
```

**Manual, through the application:**

- [ ] An administrator can sign in.
- [ ] The dashboard loads and renders without error.
- [ ] Project and bug counts look plausible for the point in time the
      backup was taken (not zero, not obviously truncated).
- [ ] An existing comment (predating the restore) is readable on its bug.
- [ ] An existing notification (predating the restore) is visible.
- [ ] At least one known attachment (predating the restore) downloads
      successfully, and its contents are intact.
- [ ] Creating a new bug works.
- [ ] Creating a new comment works.
- [ ] Uploading a new attachment works.
- [ ] The Celery worker actually processes a notification task (e.g.
      trigger a mention or assignment and confirm the recipient's
      notification appears — proves the worker is not just "up" per its
      healthcheck but genuinely consuming from the broker).

## 10. Failure and rollback guidance

- **If a backup fails partway through** (`scripts/backup.sh` returns
  nonzero): the recovery-set directory is left in place with
  `status=failed` (or, if the failure was early enough that `manifest.txt`
  was never written, an incomplete directory with no manifest at all) —
  never `status=complete`. Do not treat it as usable. Diagnose from the
  script's stderr output, delete the failed directory once you've extracted
  what you need from the logs, and re-run.
- **If a database restore fails during `pg_restore`** (step 5 above): the
  target database may be left partially restored — the script reports this
  explicitly rather than silently continuing to run migrations against a
  half-restored schema. `backend`/`celery_worker` are **not** automatically
  restarted in this case, so the application stays down rather than serving
  traffic against a broken database. Investigate the `pg_restore` output,
  then either retry the restore from the same (still-valid) dump, or drop
  back to a known-good state if one exists (e.g. the database as it was
  immediately before you started, if you took a fresh backup first — see
  the maintenance-window guidance in
  [Consistency limitations](#consistency-limitations)).
- **If an attachment restore fails during extraction/validation**: the real
  `/data/attachments` volume was never touched — the failure happened
  entirely in the staging directory. Safe to just fix the input (or use a
  different recovery set) and retry.
- **If an attachment restore fails during the clear-and-copy step**: the
  volume may be in a partial state (some old files deleted, not all new
  ones copied in yet). The script reports this explicitly.
  `backend`/`celery_worker` are not automatically restarted. Re-run the
  restore from the same validated archive — the clear-and-copy step is
  idempotent (it always clears first, then copies the full staged set).
- **Migration reversal is never part of restore.** `manage.py migrate` only
  moves forward. If a dump predates a schema change that has since shipped,
  restoring it and running `migrate` brings the schema up to the *current*
  code's expectations — it does not, and cannot, undo application code
  changes that already assume the newer schema. If you need to run older
  application code against an older dump, that is a deployment/rollback
  decision outside the scope of this document, not something these scripts
  attempt.
- **Redis is never restored.** After any restore, Celery's broker/result
  backend and the analytics cache simply start empty — this is expected and
  requires no action (see [Scope and assumptions](#1-scope-and-assumptions)).

## 11. Retention and encryption guidance

- **Retention is operator policy, not something this tooling enforces.**
  Neither `scripts/backup.sh` nor any other script here deletes old recovery
  sets. Decide a retention window appropriate to your compliance/operational
  needs and enforce it with your own scheduling (cron, a lifecycle policy on
  whatever off-site storage you copy backups to, etc).
- **Store backups outside this repository, on a volume dedicated to
  backups.** `scripts/backup.sh` refuses to write inside the repo; this is
  a hard rule, not a default that can be quietly overridden.
- **Restrictive permissions**: every artifact (`database.dump`,
  `attachments.tar.gz`, `checksums.sha256`, `manifest.txt`) is written
  `chmod 600`, and the recovery-set directory itself is `chmod 700`. A
  `database.dump` contains full application data (including personal data
  in accounts/comments) — treat it with the same sensitivity as the
  production database itself.
- **Encryption at rest**: this tooling does not encrypt backups itself, and
  deliberately does not invent a key-management scheme. If your compliance
  requirements call for encryption at rest, encrypt the recovery-set
  directory (or the volume/filesystem it lives on) with your organization's
  existing key-management tooling — e.g. an encrypted backup volume, or
  `gpg --encrypt` / `age` against the recovery-set directory using keys you
  already manage elsewhere. Do not roll your own key storage for this.
- **Off-site copies**: keep at least one copy of each retained recovery set
  somewhere other than the production host — a second host, object storage,
  wherever your organization already keeps off-site backups. A recovery set
  that only ever exists on the machine it might need to recover from is not
  a real disaster-recovery plan.
- **Backups never include `.env`.** Nothing in `scripts/backup.sh`,
  `scripts/backup_db.sh`, or `scripts/backup_attachments.sh` reads or copies
  `.env` — the database dump contains application data, not the secrets
  used to connect to it, and the attachments archive is a plain filesystem
  tar of the attachments root only.
- **Restoration requires trusted archives.** The path-traversal validation
  in [Path traversal protection](#path-traversal-protection) defends
  against a corrupted or tampered *archive structure*, not against
  restoring genuinely malicious *data* from a source you don't trust in the
  first place. Only restore from a recovery set you produced yourself (or
  received through a channel you trust as much as you trust your own
  backups).

## 12. Troubleshooting

**`refusing to overwrite existing path` / `refusing to overwrite existing
file`**
The output path (or the timestamped recovery-set directory) already exists.
Backups never overwrite — pick a new destination, or remove the old one
first if you're sure you don't need it.

**`refusing to proceed without --confirm-restore`**
Exactly what it says — pass `--confirm-restore` (or use the `make
restore-*-confirm IN=...` targets, which pass it for you, but still require
`IN=`).

**`checksum mismatch for ... — refusing to restore an unverified artifact`**
The file's contents don't match `checksums.sha256`. Don't proceed. Either
the file was corrupted/truncated in transit or storage, or it's not actually
the file the checksum file describes. Re-copy the recovery set from its
source and re-verify before trying again.

**`manifest.txt status is not 'complete'`**
The backup that produced this recovery set failed partway through (see
[Failure and rollback guidance](#10-failure-and-rollback-guidance)). Do not
restore from it — find a different, complete recovery set.

**`pg_dump failed` / `pg_restore --list could not read the dump`**
Usually means `db` isn't reachable (check `docker compose -f
docker-compose.prod.yml ps db` is healthy) or the `db` container's
`POSTGRES_USER`/`POSTGRES_DB` don't match what you expect — check `.env`.

**`tar failed while archiving attachments` / archive verification failure**
Usually means the `attachments_data` volume isn't mounted where expected,
or the `backend` image hasn't been built yet (`make prod-build`).

**Restore appears to hang at "Terminating any remaining sessions"**
A very long-running query or an orphaned connection can delay
`pg_terminate_backend`. Check `docker compose -f docker-compose.prod.yml
exec db psql -U <user> -d postgres -c "SELECT pid, state, query FROM
pg_stat_activity WHERE datname = '<db>';"` in another terminal.

**`could not determine database credentials from the 'db' container's own
environment`**
The `db` service isn't running, or its environment doesn't have
`POSTGRES_USER`/`POSTGRES_DB` set — check `.env` and `docker compose -f
docker-compose.prod.yml ps db`.

**Health/readiness checks fail after restore but the application otherwise
looks fine**
Re-run `docker compose -f docker-compose.prod.yml --env-file .env run --rm
backend python manage.py check_attachment_storage` directly — it's the same
check `/api/health/ready/` runs, with a clearer error message if the
attachments volume didn't come back writable after restore.
