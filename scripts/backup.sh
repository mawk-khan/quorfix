#!/usr/bin/env bash
# scripts/backup.sh — coordinated PostgreSQL + local-attachments backup for
# Quorfix's production Compose stack. Treats the database and the
# attachment volume as one recovery set: see docs/BACKUP_AND_RESTORE.md for
# why they must always be backed up and restored together, and for this
# script's consistency limitations (it does not stop application traffic,
# so the two artifacts are not a transactionally synchronized snapshot —
# that requires a maintenance window, documented separately).
#
# Usage:
#   scripts/backup.sh [-f COMPOSE_FILE] [-e ENV_FILE] <destination-parent-dir>
#
# Writes a new, timestamped recovery-set directory under
# <destination-parent-dir>:
#
#   quorfix-backup-YYYYmmddTHHMMSSZ/
#     manifest.txt
#     database.dump
#     attachments.tar.gz
#     checksums.sha256
#
# This is only a naming convention — restore_db.sh/restore_attachments.sh
# take a direct path to database.dump/attachments.tar.gz and never inspect
# or require any particular parent-directory name (only manifest.txt's
# format_version is validated).
#
# <destination-parent-dir> is caller-supplied and must already exist —
# this script never writes into the repository and never invents a
# default location. manifest.txt's status field only ever reads
# "complete" once every step below has succeeded and been verified; on any
# failure the directory is left in place (for diagnostics) with status
# left at "in_progress" or updated to "failed", and the script exits
# nonzero. Redis is intentionally not included — see
# docs/BACKUP_AND_RESTORE.md.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

# MANIFEST_FORMAT_VERSION is defined in lib/common.sh, shared with the
# restore scripts' manifest validation so the two can never drift apart.
# Must match ATTACHMENTS_LOCAL_ROOT on docker-compose.prod.yml's
# backend/celery_worker services — recorded in the manifest for operators,
# not read back programmatically by this script.
ATTACHMENTS_PATH_IN_CONTAINER="/data/attachments"
DATABASE_SERVICE="db"

usage() {
  cat >&2 <<USAGE
Usage: $(basename "$0") [-f COMPOSE_FILE] [-e ENV_FILE] <destination-parent-dir>

  -f COMPOSE_FILE           Compose file to use (default: $DEFAULT_COMPOSE_FILE)
  -e ENV_FILE               Env file passed as --env-file (default: $DEFAULT_ENV_FILE)
  <destination-parent-dir>  Existing directory to create the timestamped
                             recovery-set directory in. Never a path inside
                             this repository.
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

[ "$#" -eq 1 ] || usage
DEST_PARENT="$1"

require_cmd docker
require_cmd tar
require_cmd date
[ -f "$COMPOSE_FILE" ] || die "compose file not found: $COMPOSE_FILE"
[ -d "$DEST_PARENT" ] || die "destination directory does not exist: $DEST_PARENT"

case "$(cd -- "$DEST_PARENT" && pwd)" in
  "$REPO_ROOT" | "$REPO_ROOT"/*)
    die "refusing to write a backup inside the repository ($REPO_ROOT) — pass a destination outside it"
    ;;
esac

log "Validating Compose configuration ..."
compose config >/dev/null || die "docker compose config failed for $COMPOSE_FILE / $ENV_FILE"

# Soft, best-effort disk-space warning — never blocks the backup, since
# actual space needed depends entirely on database/attachment volume size,
# which this script has no cheap way to predict up front.
if command -v df >/dev/null 2>&1; then
  available_kb="$(df -Pk "$DEST_PARENT" 2>/dev/null | awk 'NR==2 {print $4}')"
  if [ -n "${available_kb:-}" ] && [ "$available_kb" -lt 512000 ] 2>/dev/null; then
    log "warning: less than 500MB free at $DEST_PARENT — verify there is enough space for this backup"
  fi
fi

TIMESTAMP="$(utc_timestamp)"
BACKUP_DIR="${DEST_PARENT%/}/quorfix-backup-${TIMESTAMP}"
refuse_if_exists "$BACKUP_DIR"

mkdir -- "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

MANIFEST="$BACKUP_DIR/manifest.txt"
DB_DUMP="$BACKUP_DIR/database.dump"
ATTACHMENTS_ARCHIVE="$BACKUP_DIR/attachments.tar.gz"
CHECKSUMS="$BACKUP_DIR/checksums.sha256"

FAILED=0
on_exit() {
  status=$?
  if [ "$status" -ne 0 ] || [ "$FAILED" -ne 0 ]; then
    log "Backup FAILED — leaving $BACKUP_DIR in place for diagnostics (status is not 'complete')."
    if [ -f "$MANIFEST" ]; then
      write_manifest_status "failed"
    fi
    exit 1
  fi
}
trap on_exit EXIT

write_manifest_status() {
  # Rewrites only the status= line, atomically, leaving every other field
  # untouched. manifest.txt is deliberately outside checksums.sha256 (see
  # the module docstring), so rewriting it after checksums are generated
  # creates no circular-checksum problem.
  tmp="${MANIFEST}.tmp.$$"
  awk -v new_status="status=$1" '
    /^status=/ { print new_status; next }
    { print }
  ' "$MANIFEST" >"$tmp"
  mv -- "$tmp" "$MANIFEST"
}

GIT_SHA="unknown"
if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse HEAD >/dev/null 2>&1; then
  GIT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
fi
APP_VERSION="${VERSION:-unknown}"

MIGRATIONS_SUMMARY="unavailable"
if compose exec -T backend python manage.py showmigrations --plan >"${BACKUP_DIR}/.migrations-plan.tmp" 2>/dev/null; then
  applied="$(grep -c '^\[X\]' "${BACKUP_DIR}/.migrations-plan.tmp" || true)"
  unapplied="$(grep -c '^\[ \]' "${BACKUP_DIR}/.migrations-plan.tmp" || true)"
  MIGRATIONS_SUMMARY="applied=${applied} unapplied=${unapplied}"
fi
rm -f -- "${BACKUP_DIR}/.migrations-plan.tmp"

cat >"$MANIFEST" <<MANIFEST_EOF
# Quorfix coordinated recovery-set manifest. See docs/BACKUP_AND_RESTORE.md.
format_version=$MANIFEST_FORMAT_VERSION
status=in_progress
timestamp_utc=$TIMESTAMP
app_version=$APP_VERSION
git_sha=$GIT_SHA
compose_file=$COMPOSE_FILE
database_service=$DATABASE_SERVICE
database_format=pg_dump-custom
attachment_volume=attachments_data
attachment_path_in_container=$ATTACHMENTS_PATH_IN_CONTAINER
attachment_format=tar.gz
migrations_summary=$MIGRATIONS_SUMMARY
MANIFEST_EOF
chmod 600 "$MANIFEST"

log "Recovery set: $BACKUP_DIR"

log "== Database backup =="
"$SCRIPT_DIR/backup_db.sh" -f "$COMPOSE_FILE" -e "$ENV_FILE" "$DB_DUMP" || {
  FAILED=1
  die "database backup failed"
}

log "== Attachment backup =="
"$SCRIPT_DIR/backup_attachments.sh" -f "$COMPOSE_FILE" -e "$ENV_FILE" "$ATTACHMENTS_ARCHIVE" || {
  FAILED=1
  die "attachment backup failed"
}

log "== Checksums =="
(
  cd -- "$BACKUP_DIR" && sha256_of "$(basename -- "$DB_DUMP")" "$(basename -- "$ATTACHMENTS_ARCHIVE")"
) >"$CHECKSUMS" || {
  FAILED=1
  die "checksum generation failed"
}
chmod 600 "$CHECKSUMS"

log "== Verifying checksums =="
verify_checksums "$CHECKSUMS" || {
  FAILED=1
  die "checksum self-verification failed"
}

write_manifest_status "complete"
log "Backup complete: $BACKUP_DIR"
printf '%s\n' "$BACKUP_DIR"
