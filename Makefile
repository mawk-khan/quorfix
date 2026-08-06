.PHONY: seed-demo prod-config prod-build prod-up prod-down prod-check prod-migrate

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
