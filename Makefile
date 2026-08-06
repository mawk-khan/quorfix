.PHONY: seed-demo prod-config prod-build prod-up prod-down prod-check prod-migrate \
	backup backup-db backup-attachments restore-db-confirm restore-attachments-confirm \
	prod-migrations-check prod-migrations-plan prod-upgrade-check prod-version upgrade-smoke \
	ci-backend ci-frontend ci-e2e ci-images openapi-check community-check

# Seeds local development demo data (organization, one user per Community
# role, three projects). Development-only — refuses to run under production
# settings. Requires the stack to be running (`docker compose up`).
seed-demo:
	docker compose exec backend python manage.py seed_demo

# --- Production Compose (docker-compose.prod.yml) -------------------------
#
# Every target below targets docker-compose.prod.yml explicitly — never the
# local-development docker-compose.yml. None of them run migrations or seed
# data automatically; `prod-migrate` is the explicit, separate step for that.

PROD_COMPOSE = docker compose -f docker-compose.prod.yml --env-file .env

# Validates and prints the fully-resolved production Compose configuration
# (variable substitution applied) without starting anything — the fastest
# way to check for a missing/malformed .env value.
prod-config:
	$(PROD_COMPOSE) config

# Builds the production backend and frontend images (no dev/test
# dependencies, non-root runtime users — see backend/Dockerfile and
# frontend/Dockerfile).
prod-build:
	$(PROD_COMPOSE) build

# Starts db, redis, backend, celery_worker, and frontend. Does NOT run
# migrations — run `make prod-migrate` explicitly (first deploy and after
# any model change) before or after this, as appropriate.
prod-up:
	$(PROD_COMPOSE) up -d

# Stops and removes the production containers. Named volumes
# (postgres_data, redis_data, attachments_data) are left intact — this does
# not delete data.
prod-down:
	$(PROD_COMPOSE) down

# Runs Django's system checks (including every apps.core.checks
# bugfixer.E0xx production check) against the production image and current
# .env, without starting the long-running services. The backend's own
# entrypoint already runs this on every container start; this target is for
# checking configuration before deploying at all.
prod-check:
	$(PROD_COMPOSE) run --rm backend python manage.py check

# Explicit, separate step — never run automatically by prod-up. Take a
# database backup first (see docs/BACKUP_AND_RESTORE.md, a later Phase 6
# chunk) before running this against a production database with existing
# data.
prod-migrate:
	$(PROD_COMPOSE) run --rm backend python manage.py migrate

# --- Upgrade checks (see docs/UPGRADING.md) --------------------------------
#
# Non-destructive — none of these apply migrations or start/stop services.
# Confirmed behavior (see docs/UPGRADING.md "Migration checks"):
#   makemigrations --check --dry-run: nonzero if any model change has no
#     migration file yet (drift); does NOT write the missing file.
#   showmigrations --plan: always exits 0 — read its [X]/[ ] output, don't
#     rely on its exit code.
#   migrate --check: nonzero if any existing migration file is unapplied;
#     does NOT apply it. Unrelated to drift — a model change with no
#     migration file yet does not make this fail; only makemigrations
#     --check catches that.

# Fails if there are model changes with no corresponding migration file.
prod-migrations-check:
	$(PROD_COMPOSE) run --rm backend python manage.py makemigrations --check --dry-run

# Always exits 0 — informational only. Read the printed plan.
prod-migrations-plan:
	$(PROD_COMPOSE) run --rm backend python manage.py showmigrations --plan

# Combined pre-upgrade gate: validates the resolved Compose config, then
# fails on migration drift, then fails on any unapplied migration. Run this
# before every upgrade; see docs/UPGRADING.md step "Check migration plan".
prod-upgrade-check:
	$(PROD_COMPOSE) config >/dev/null
	$(PROD_COMPOSE) run --rm backend python manage.py makemigrations --check --dry-run
	$(PROD_COMPOSE) run --rm backend python manage.py migrate --check

# Prints the locally built backend/frontend images' OCI labels (version,
# revision, source, digest) — see docs/UPGRADING.md "Version metadata".
prod-version:
	scripts/inspect_version.sh

# Non-destructive post-upgrade smoke check (Compose config, liveness,
# readiness, frontend, migration status, Celery worker container state) —
# see scripts/upgrade_smoke.sh and docs/UPGRADING.md.
upgrade-smoke:
	scripts/upgrade_smoke.sh $(if $(COMPOSE_FILE),-f $(COMPOSE_FILE)) $(if $(ENV_FILE),-e $(ENV_FILE))

# --- Backup / restore (scripts/backup*.sh, scripts/restore*.sh) -----------
#
# Full procedure: docs/BACKUP_AND_RESTORE.md. Every target below defaults
# to docker-compose.prod.yml and .env, same as the prod-* targets above;
# pass COMPOSE_FILE=/ENV_FILE= to override. Restore targets are destructive
# and deliberately named *-confirm — they still require an explicit IN=
# path on top of that, so a bare `make restore-db-confirm` refuses to run.

# Coordinated database + attachments backup. Usage:
#   make backup DEST=/path/outside/repo
backup:
	@test -n "$(DEST)" || (echo "usage: make backup DEST=/path/outside/repo" >&2; exit 2)
	scripts/backup.sh $(if $(COMPOSE_FILE),-f $(COMPOSE_FILE)) $(if $(ENV_FILE),-e $(ENV_FILE)) "$(DEST)"

# Database-only backup. Usage:
#   make backup-db OUT=/path/outside/repo/database.dump
backup-db:
	@test -n "$(OUT)" || (echo "usage: make backup-db OUT=/path/to/database.dump" >&2; exit 2)
	scripts/backup_db.sh $(if $(COMPOSE_FILE),-f $(COMPOSE_FILE)) $(if $(ENV_FILE),-e $(ENV_FILE)) "$(OUT)"

# Attachments-only backup. Usage:
#   make backup-attachments OUT=/path/outside/repo/attachments.tar.gz
backup-attachments:
	@test -n "$(OUT)" || (echo "usage: make backup-attachments OUT=/path/to/attachments.tar.gz" >&2; exit 2)
	scripts/backup_attachments.sh $(if $(COMPOSE_FILE),-f $(COMPOSE_FILE)) $(if $(ENV_FILE),-e $(ENV_FILE)) "$(OUT)"

# Destructive: drops and recreates the target database. Usage:
#   make restore-db-confirm IN=/path/to/database.dump
restore-db-confirm:
	@test -n "$(IN)" || (echo "usage: make restore-db-confirm IN=/path/to/database.dump" >&2; exit 2)
	scripts/restore_db.sh $(if $(COMPOSE_FILE),-f $(COMPOSE_FILE)) $(if $(ENV_FILE),-e $(ENV_FILE)) --confirm-restore "$(IN)"

# Destructive: replaces the entire attachments volume. Usage:
#   make restore-attachments-confirm IN=/path/to/attachments.tar.gz
restore-attachments-confirm:
	@test -n "$(IN)" || (echo "usage: make restore-attachments-confirm IN=/path/to/attachments.tar.gz" >&2; exit 2)
	scripts/restore_attachments.sh $(if $(COMPOSE_FILE),-f $(COMPOSE_FILE)) $(if $(ENV_FILE),-e $(ENV_FILE)) --confirm-restore "$(IN)"

# --- CI-equivalent targets (mirror .github/workflows/*.yml) ----------------
#
# These run the same command sequences as CI, locally, via the scripts in
# scripts/ci_*.sh — see each script's own header for exactly what it does
# and does not touch. None of these push images or tag a release.

# Requires docker-compose.yml's backend/celery_worker already running
# (`docker compose up -d db redis backend celery_worker`). Includes
# pip-audit (blocking, same as .github/workflows/backend.yml — see
# docs/SECURITY.md "Dependency scan policy").
ci-backend:
	scripts/ci_backend.sh

# Requires docker-compose.yml's frontend already running
# (`docker compose up -d frontend`).
ci-frontend:
	scripts/ci_frontend.sh

# Destructive to the dev stack's current database — see scripts/ci_e2e.sh's
# own header. Backs up and restores your .env automatically; always tears
# the stack down (including its volumes) when it finishes.
ci-e2e:
	scripts/ci_e2e.sh

# Builds both production images fresh (no dev stack required) and verifies
# them — never pushes anywhere.
ci-images:
	scripts/ci_images.sh

# Requires docker-compose.yml's backend already running.
openapi-check:
	docker compose exec backend python manage.py spectacular --file /tmp/schema.yml --validate

# Requires docker-compose.yml's backend already running.
community-check:
	docker compose exec backend sh -c 'test ! -f professional/apps.py'
	docker compose exec backend pytest \
		apps/attachments/tests/test_community_isolation.py \
		apps/comments/tests/test_community_isolation.py \
		apps/notifications/tests/test_community_isolation.py -v
