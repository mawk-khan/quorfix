#!/usr/bin/env bash
# scripts/upgrade_smoke.sh — non-destructive post-upgrade smoke check for
# Quorfix's production Compose stack. See docs/UPGRADING.md step "Run
# post-upgrade smoke tests".
#
# Usage:
#   scripts/upgrade_smoke.sh [-f COMPOSE_FILE] [-e ENV_FILE]
#
# Verifies:
#   - the Compose configuration resolves
#   - backend liveness (/api/health/)
#   - backend readiness (/api/health/ready/)
#   - frontend responds
#   - no unapplied migrations remain
#   - the celery_worker container is running
#
# Every check here is read-only: nothing is created, deleted, or modified,
# no demo credentials are used, and no secret is ever printed. This script
# proves the *container* is alive and the *migration state* is caught up —
# it deliberately does NOT claim notifications are actually delivered (that
# needs a real task dispatched and its result observed, which touches
# application data and is documented as a manual post-upgrade step in
# docs/UPGRADING.md instead — see "Verify attachments and notifications").

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat >&2 <<USAGE
Usage: $(basename "$0") [-f COMPOSE_FILE] [-e ENV_FILE]

  -f COMPOSE_FILE   Compose file to use (default: $DEFAULT_COMPOSE_FILE)
  -e ENV_FILE       Env file passed as --env-file (default: $DEFAULT_ENV_FILE)
USAGE
  exit 2
}

while getopts ":f:e:h" opt; do
  case "$opt" in
    f) COMPOSE_FILE="$OPTARG" ;;
    e) ENV_FILE="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))
[ "$#" -eq 0 ] || usage

require_cmd docker
[ -f "$COMPOSE_FILE" ] || die "compose file not found: $COMPOSE_FILE"

FAILED=0
check() {
  desc="$1"
  shift
  printf '%-45s' "$desc"
  if "$@" >/tmp/upgrade-smoke-out.$$ 2>&1; then
    echo "OK"
  else
    echo "FAILED"
    sed 's/^/    /' /tmp/upgrade-smoke-out.$$ >&2
    FAILED=1
  fi
  rm -f /tmp/upgrade-smoke-out.$$
}

check "Compose configuration resolves" compose config
check "Backend liveness (/api/health/)" \
  compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health/', timeout=5)"
check "Backend readiness (/api/health/ready/)" \
  compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health/ready/', timeout=5)"
check "Frontend responds" \
  compose exec -T frontend node -e "fetch('http://127.0.0.1:3000/').then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
check "No unapplied migrations" \
  compose exec -T backend python manage.py migrate --check

_celery_worker_container_running() {
  compose ps --status running --services | grep -qx celery_worker
}
check "celery_worker container is running (not: tasks are being processed)" \
  _celery_worker_container_running

echo
if [ "$FAILED" -eq 0 ]; then
  log "All smoke checks passed."
else
  die "One or more smoke checks failed — see output above."
fi
