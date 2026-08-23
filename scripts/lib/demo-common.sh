#!/usr/bin/env bash
# scripts/lib/demo-common.sh — shared helpers for scripts/demo. A library:
# sourced only, never executed directly. Layers demo-specific safety checks
# (environment identification, allow-listed service names) on top of
# scripts/lib/common.sh's generic Compose/backup helpers, which this file
# also sources — callers of demo-common.sh get both.

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "scripts/lib/demo-common.sh is a library — source it, don't run it directly." >&2
  exit 1
fi

SCRIPTS_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)"
# shellcheck source=common.sh
. "$SCRIPTS_DIR/lib/common.sh"

# Every service docker-compose.prod.yml actually defines. Command names and
# `logs` targets are validated against this fixed list before ever being
# interpolated into a `docker compose` invocation — an arbitrary
# caller-supplied string is never accepted as a service name.
DEMO_SERVICES=(db redis backend celery_worker frontend)

is_known_service() {
  candidate="$1"
  for known in "${DEMO_SERVICES[@]}"; do
    if [ "$candidate" = "$known" ]; then
      return 0
    fi
  done
  return 1
}

require_docker() {
  require_cmd docker
  docker compose version >/dev/null 2>&1 || die "docker compose (the v2 plugin) is not available on PATH"
}

# Prints which compose/env file this invocation resolved to. Called by
# every lifecycle command before it does anything, so an operator always
# sees what they are about to affect.
print_environment_banner() {
  log "Compose file: $COMPOSE_FILE"
  log "Env file:     $ENV_FILE"
}

# The core "don't operate on the wrong environment by accident" gate (see
# docs/DEMO_DEPLOYMENT.md "Isolation boundary"). Requires:
#   - the resolved env file to exist
#   - it to declare QUORFIX_ENV=demo verbatim, on its own line
#
# Deliberately a plain grep, never `source`/`.`-ing the env file itself —
# that would execute arbitrary shell from a file an operator controls, for
# the sake of reading one variable. docker compose's own --env-file loading
# (via the compose() wrapper) is what actually applies the file's values;
# this check only ever decides whether to proceed at all.
require_demo_env() {
  [ -f "$ENV_FILE" ] || die "env file not found: $ENV_FILE
Copy .env.example to $ENV_FILE and set QUORFIX_ENV=demo (see docs/DEMO_DEPLOYMENT.md)."
  grep -qx 'QUORFIX_ENV=demo' "$ENV_FILE" || die "$ENV_FILE does not declare QUORFIX_ENV=demo
Refusing to run a demo lifecycle command against a file that isn't explicitly marked
as the demo environment. Add the line 'QUORFIX_ENV=demo' to $ENV_FILE."
}

# Fails fast with Compose's own clear error on a malformed/missing value,
# before any lifecycle action (build, migrate, up, ...) runs.
validate_compose_config() {
  compose config >/dev/null || die "docker compose config failed for $COMPOSE_FILE / $ENV_FILE"
}
