#!/usr/bin/env bash
# scripts/restore_db.sh — destructive PostgreSQL restore for Bug Fixer's
# production Compose stack (docker-compose.prod.yml's `db` service).
#
# Usage:
#   scripts/restore_db.sh [-f COMPOSE_FILE] [-e ENV_FILE] --confirm-restore <dump-file>
#
# THIS IS DESTRUCTIVE. It drops and recreates the target database, so an
# existing database is fully replaced by the dump's contents. There is no
# interactive prompt — --confirm-restore must be passed explicitly (this is
# also what makes the script safe in CI/non-TTY contexts: there is no
# ambiguous prompt to hang on or auto-answer).
#
# Requires <dump-file> to sit next to a checksums.sha256 that lists it (see
# scripts/backup.sh) — the checksum is verified before anything is
# mutated. If a manifest.txt is also present in that directory, its
# format_version and status=complete are checked too.
#
# Procedure (see docs/BACKUP_AND_RESTORE.md for the full write-up):
#   1. Validate the dump file, checksum, and manifest.
#   2. Stop `backend` and `celery_worker` (db and redis keep running).
#   3. Terminate any remaining sessions on the target database.
#   4. Drop and recreate the target database (this restore's chosen
#      strategy — not `pg_restore --clean --if-exists` into a
#      pre-existing database; see docs/BACKUP_AND_RESTORE.md for why).
#   5. pg_restore the dump into the fresh database.
#   6. Run Django migrations (forward only — this never reverts
#      migrations; a dump backed up from an older code version still
#      needs the current code's migrations applied after restore).
#   7. Restart `backend` and `celery_worker`.
#
# Never run this against a database that is still receiving application
# writes — step 2 is what makes that true for the rest of the procedure.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat >&2 <<USAGE
Usage: $(basename "$0") [-f COMPOSE_FILE] [-e ENV_FILE] --confirm-restore <dump-file>

  -f COMPOSE_FILE     Compose file to use (default: $DEFAULT_COMPOSE_FILE)
  -e ENV_FILE         Env file passed as --env-file (default: $DEFAULT_ENV_FILE)
  --confirm-restore   Required. This operation drops and recreates the
                       target database — there is no other confirmation.
  <dump-file>         pg_dump custom-format archive to restore (must have a
                       checksums.sha256 listing it in the same directory —
                       see scripts/backup.sh).
USAGE
  exit 2
}

# Checked against the original, unmodified argument list — a fixed literal
# flag, never a prompt, so there is nothing here that behaves differently
# in an interactive shell vs. CI/non-TTY.
require_confirm_flag "$@"

DUMP_FILE=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -f)
      COMPOSE_FILE="$2"
      shift 2
      ;;
    -e)
      ENV_FILE="$2"
      shift 2
      ;;
    --confirm-restore)
      shift
      ;;
    -h | --help)
      usage
      ;;
    -*)
      usage
      ;;
    *)
      DUMP_FILE="$1"
      shift
      ;;
  esac
done

[ -n "$DUMP_FILE" ] || usage

# Validate the input itself first — pure filesystem work, no Docker
# involved — before checking that Docker/the Compose file are even
# available. Cheapest, most informative checks first.
log "Validating dump file, checksum, and manifest ..."
require_verified_artifact "$DUMP_FILE"

require_cmd docker
[ -f "$COMPOSE_FILE" ] || die "compose file not found: $COMPOSE_FILE"

log "Stopping backend and celery_worker (db and redis stay running) ..."
compose stop backend celery_worker

TARGET_USER="$(compose exec -T db sh -c 'printf "%s" "$POSTGRES_USER"')"
TARGET_DB="$(compose exec -T db sh -c 'printf "%s" "$POSTGRES_DB"')"
[ -n "$TARGET_USER" ] && [ -n "$TARGET_DB" ] || die "could not determine database credentials from the 'db' container's own environment"

log "Terminating any remaining sessions on database '$TARGET_DB' ..."
compose exec -T db psql -U "$TARGET_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$TARGET_DB' AND pid <> pg_backend_pid();
SQL

log "Dropping and recreating database '$TARGET_DB' ..."
compose exec -T db psql -U "$TARGET_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
DROP DATABASE IF EXISTS "$TARGET_DB";
CREATE DATABASE "$TARGET_DB" OWNER "$TARGET_USER";
SQL

log "Restoring dump into '$TARGET_DB' ..."
if ! compose exec -T db pg_restore --username "$TARGET_USER" --dbname "$TARGET_DB" --no-owner <"$DUMP_FILE"; then
  die "pg_restore failed — database '$TARGET_DB' may be left partially restored. Investigate before restarting backend/celery_worker."
fi

log "Running Django migrations (forward only) ..."
compose run --rm backend python manage.py migrate --noinput

log "Restarting backend and celery_worker ..."
compose up -d backend celery_worker

log "Database restore complete. Run the post-restore verification checklist in docs/BACKUP_AND_RESTORE.md next."
