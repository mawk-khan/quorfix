#!/usr/bin/env bash
# scripts/ci_e2e.sh — runs the exact E2E reset/startup/test sequence
# (.github/workflows/e2e.yml) locally against docker-compose.yml.
#
# THIS IS DESTRUCTIVE to whatever is currently in the dev stack's
# database: frontend/e2e/global-setup.ts flushes it and reseeds only the
# deterministic E2E fixtures. To protect your actual local dev data, this
# script:
#   - backs up your current .env (if any) and restores it on exit
#   - always tears the stack down (`docker compose down -v`, removing the
#     postgres_data volume) on exit, success or failure alike
# — so a normal local dev session is unaffected once this script finishes,
# but do not run it while you have unsaved local dev data you still need
# *during* the run (e.g. in another terminal against the same stack).
#
# Usage: scripts/ci_e2e.sh

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

require_cmd docker
require_cmd npm
require_cmd node
require_cmd curl

# Playwright itself runs on whatever `node` is on the caller's PATH here
# (there is no Docker container for it — see the header comment) — must
# match frontend/Dockerfile's node:22-slim and .github/workflows/{frontend,
# e2e}.yml's setup-node "22", not whatever the host happens to have. An old
# host Node (e.g. 14) doesn't fail cleanly here; `npm ci` just breaks with
# an opaque "Cannot read property 'next' of undefined", so check explicitly
# and say so.
node_major="$(node -e 'process.stdout.write(String(process.versions.node.split(".")[0]))')"
if [ "$node_major" -lt 22 ]; then
  die "node on PATH is $(node --version), but this script needs Node 22+ (matching frontend/Dockerfile and CI) — install/activate Node 22 (e.g. via nvm) before running scripts/ci_e2e.sh. The rest of the stack (backend/celery_worker/frontend) is unaffected — it runs in Docker regardless of the host's Node version."
fi

COMPOSE_FILE="docker-compose.yml"
ENV_BACKUP=""

cleanup() {
  log "Tearing down (docker compose down -v) ..."
  docker compose -f "$COMPOSE_FILE" down -v || true
  if [ -n "$ENV_BACKUP" ]; then
    mv -f "$ENV_BACKUP" "$REPO_ROOT/.env"
    log "Restored your original .env."
  fi
}
trap cleanup EXIT

cd "$REPO_ROOT"

if [ -f .env ]; then
  ENV_BACKUP="$(mktemp)"
  cp .env "$ENV_BACKUP"
  log "Backed up your existing .env — it will be restored when this script exits."
fi
cp .env.example .env

# Installed before any `docker compose` command runs — same reason as
# .github/workflows/e2e.yml's step order: docker-compose.yml's frontend
# service bind-mounts ./frontend:/app with a nested volume isolating
# /app/node_modules from the host. On a checkout with no
# ./frontend/node_modules yet, the *first* `docker compose up` still has
# to create a mount point for that nested volume at the host path (root-
# owned), which then blocks this exact `npm ci` with EACCES. Running
# `npm ci` first means the directory already exists, host-user-owned, so
# Docker reuses it instead of creating it fresh.
log "Installing Playwright's own dependencies ..."
(cd frontend && npm ci)

log "Building images ..."
docker compose -f "$COMPOSE_FILE" build

log "Starting db, redis, backend, celery_worker, frontend ..."
docker compose -f "$COMPOSE_FILE" up -d

log "Waiting for backend ..."
backend_ready=0
for _ in $(seq 1 30); do
  curl -sf http://localhost:8000/api/health/ >/dev/null && backend_ready=1 && break
  sleep 1
done
[ "$backend_ready" -eq 1 ] || {
  docker compose -f "$COMPOSE_FILE" logs backend
  die "Backend did not become ready in time"
}

log "Waiting for Celery worker ..."
celery_ready=0
for _ in $(seq 1 30); do
  docker compose -f "$COMPOSE_FILE" exec -T celery_worker celery -A config inspect ping >/dev/null 2>&1 && celery_ready=1 && break
  sleep 1
done
[ "$celery_ready" -eq 1 ] || {
  docker compose -f "$COMPOSE_FILE" logs celery_worker
  die "Celery worker did not become ready in time"
}

log "Waiting for frontend ..."
frontend_ready=0
for _ in $(seq 1 60); do
  curl -sf http://localhost:3000 >/dev/null && frontend_ready=1 && break
  sleep 1
done
[ "$frontend_ready" -eq 1 ] || {
  docker compose -f "$COMPOSE_FILE" logs frontend
  die "Frontend did not become ready in time"
}

log "Applying migrations ..."
docker compose -f "$COMPOSE_FILE" exec -T backend python manage.py migrate --no-input

log "Installing Playwright's Chromium browser ..."
(cd frontend && npx playwright install --with-deps chromium)

log "Running the full Playwright suite (global-setup.ts resets and reseeds fixtures) ..."
(cd frontend && npx playwright test)

log "E2E CI sequence passed."
