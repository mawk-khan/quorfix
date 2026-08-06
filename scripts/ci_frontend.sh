#!/usr/bin/env bash
# scripts/ci_frontend.sh — runs the exact frontend CI sequence
# (.github/workflows/frontend.yml) locally, against an already-running
# docker-compose.yml dev stack (`docker compose up -d frontend` first).
#
# Usage: scripts/ci_frontend.sh

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

COMPOSE_FILE="docker-compose.yml"

run() {
  echo "+ $*" >&2
  docker compose -f "$COMPOSE_FILE" exec -T -e NEXT_TELEMETRY_DISABLED=1 frontend "$@"
}

run npm ci
run npm run lint
run npm run typecheck
run npm run test
run npm run build
run npm audit --audit-level=high

log "Frontend CI sequence passed."
