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

## 4. Demo data reset

**The existing seed + backup/restore architecture is already sufficient for a safe, repeatable
demo reset — no new destructive command was written for this.** `seed_demo` is idempotent (see
`backend/apps/core/tests/test_seed_demo.py`), and `scripts/restore_db.sh`/
`scripts/restore_attachments.sh` (see `docs/BACKUP_AND_RESTORE.md`) are already exactly
"stop writes → replace the database wholesale → migrate → restart", already tested
(`scripts/tests/test_backup_restore_guards.sh`), and already require an explicit
`--confirm-restore` flag plus a checksum-verified dump. Reusing them for the demo reset means
the reset relies on the same hardened path as disaster recovery, rather than new,
independently-risky code.

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

**Not yet built: an automatic schedule.** Per this pass's scope, no cron/scheduled job runs the
above automatically — an operator (or a scheduled CI/ops job, added separately when the demo is
actually deployed) triggers a reset manually using the two commands above. Automating that
schedule is a reasonable next step once the demo is live and an actual reset cadence (e.g.
nightly) is decided, but is out of scope here.

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
