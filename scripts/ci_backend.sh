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
  docker compose -f "$COMPOSE_FILE" exec -T backend "$@"
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

log "Backend CI sequence passed. (pip-audit is non-blocking in CI — run 'make ci-backend-audit' separately if you want it locally.)"
