#!/usr/bin/env bash
# scripts/ci_backend.sh — runs the exact backend CI sequence
# (.github/workflows/backend.yml) locally, against an already-running
# docker-compose.yml dev stack (`docker compose up -d db redis backend
# celery_worker` first). Mirrors the workflow step order; does not start
# the stack itself, since developers typically already have it running.
#
# Usage: scripts/ci_backend.sh

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

COMPOSE_FILE="docker-compose.yml"

run() {
  echo "+ $*" >&2
  # .github/workflows/backend.yml sets DJANGO_SETTINGS_MODULE=config.settings.test
  # job-wide for every step below. Without this override, `docker compose exec`
  # silently inherits the backend container's own DJANGO_SETTINGS_MODULE
  # (config.settings.development per docker-compose.yml), which has looser,
  # Redis-backed throttle rates shared across the whole run instead of
  # config.settings.test's per-run LocMemCache — causing this script to
  # produce results the real CI gate would not (e.g. spurious 429s from
  # rate-limited endpoints exercised many times in quick succession).
  docker compose -f "$COMPOSE_FILE" exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test backend "$@"
}

run ruff check .
run ruff format --check .
run python manage.py check
run python manage.py makemigrations --check --dry-run
run python manage.py migrate --no-input
run python manage.py migrate --check
run pytest

run sh -c 'test ! -f professional/apps.py'
run pytest \
  apps/attachments/tests/test_community_isolation.py \
  apps/comments/tests/test_community_isolation.py \
  apps/notifications/tests/test_community_isolation.py -v

run python manage.py spectacular --file /tmp/schema.yml --validate

# Blocking, same as .github/workflows/backend.yml — see docs/SECURITY.md
# "Dependency scan policy". Installed fresh each run, not added to
# requirements-dev.txt.
run sh -c 'pip install --quiet pip-audit && pip-audit -r requirements.txt'

# Blocking as of Phase 6 Chunk K — see requirements-dev.txt's own pytest
# pin comment and docs/ACCESS_AND_TESTING.md Phase 6 Chunk K.
run sh -c 'pip install --quiet pip-audit && pip-audit -r requirements-dev.txt'

log "Backend CI sequence passed."
