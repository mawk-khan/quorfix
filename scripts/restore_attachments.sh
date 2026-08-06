#!/usr/bin/env bash
# scripts/restore_attachments.sh — destructive local-attachments restore
# for Bug Fixer's production Compose stack (docker-compose.prod.yml's
# `attachments_data` named volume).
#
# Usage:
#   scripts/restore_attachments.sh [-f COMPOSE_FILE] [-e ENV_FILE] --confirm-restore <tar-file>
#
# THIS IS DESTRUCTIVE. It replaces the entire contents of the attachments
# volume with the archive's contents — old files are not merged with the
# restored ones (a silent merge could leave unreferenced leftover files
# that mask an incomplete restore). There is no interactive prompt —
# --confirm-restore must be passed explicitly.
#
# Requires <tar-file> to sit next to a checksums.sha256 that lists it (see
# scripts/backup.sh) — the checksum is verified, and every archive member
# is validated (see backend/apps/core/tar_safety.py: no absolute paths, no
# `..` traversal, no symlinks/special files), before anything is mutated.
# If a manifest.txt is also present in that directory, its format_version
# and status=complete are checked too.
#
# Procedure (see docs/BACKUP_AND_RESTORE.md for the full write-up):
#   1. Validate the archive file, checksum, and manifest.
#   2. Stop `backend` and `celery_worker` (they hold the volume mounted).
#   3. Validate and extract the archive into a staging directory *inside
#      the container* — nothing under the real attachments root is
#      touched yet, so an unsafe or corrupt archive is caught before any
#      existing file is deleted.
#   4. Clear the real attachments root and move the staged, validated
#      files into place.
#   5. Restart `backend` and `celery_worker`.
#
# This does not first snapshot the volume being replaced. If you want that
# safety net, run `scripts/backup.sh` against the current (soon-to-be-
# replaced) state before running this script.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

# Must match ATTACHMENTS_LOCAL_ROOT on docker-compose.prod.yml's
# backend/celery_worker services.
ATTACHMENTS_PATH_IN_CONTAINER="/data/attachments"

usage() {
  cat >&2 <<USAGE
Usage: $(basename "$0") [-f COMPOSE_FILE] [-e ENV_FILE] --confirm-restore <tar-file>

  -f COMPOSE_FILE     Compose file to use (default: $DEFAULT_COMPOSE_FILE)
  -e ENV_FILE         Env file passed as --env-file (default: $DEFAULT_ENV_FILE)
  --confirm-restore   Required. This operation replaces the entire
                       contents of the attachments volume — there is no
                       other confirmation.
  <tar-file>          attachments.tar.gz archive to restore (must have a
                       checksums.sha256 listing it in the same directory —
                       see scripts/backup.sh).
USAGE
  exit 2
}

require_confirm_flag "$@"

ARCHIVE_FILE=""
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
      ARCHIVE_FILE="$1"
      shift
      ;;
  esac
done

[ -n "$ARCHIVE_FILE" ] || usage

# Validate the input itself first — pure filesystem work, no Docker
# involved — before checking that Docker/the Compose file are even
# available. Cheapest, most informative checks first.
log "Validating archive file, checksum, and manifest ..."
require_verified_artifact "$ARCHIVE_FILE"

require_cmd docker
[ -f "$COMPOSE_FILE" ] || die "compose file not found: $COMPOSE_FILE"

case "$ARCHIVE_FILE" in
  /*) ARCHIVE_ABS="$ARCHIVE_FILE" ;;
  *) ARCHIVE_ABS="$(pwd)/$ARCHIVE_FILE" ;;
esac
ARCHIVE_DIR="$(dirname -- "$ARCHIVE_ABS")"
ARCHIVE_BASENAME="$(basename -- "$ARCHIVE_ABS")"

log "Stopping backend and celery_worker ..."
compose stop backend celery_worker

# A single container run, not two: the staging directory below lives under
# /tmp *inside this one container instance* — a separate `compose run`
# would start a fresh container with nothing in it, losing the staged
# files between "validate/extract" and "clear and copy into place". Doing
# both in one shell script, in this order, is what makes "validate before
# mutating the real attachments root" actually true: `set -e` means a
# failed extraction (an unsafe or corrupt archive) exits before the `find
# -delete` line ever runs.
log "Validating archive, then replacing $ATTACHMENTS_PATH_IN_CONTAINER with its contents ..."
if ! compose run --rm --no-deps \
  -v "${ARCHIVE_DIR}:/backup:ro" \
  backend sh -c "
    set -e
    rm -rf /tmp/attachments-restore-staging
    python manage.py extract_attachments_archive --archive '/backup/${ARCHIVE_BASENAME}' --destination /tmp/attachments-restore-staging
    find '$ATTACHMENTS_PATH_IN_CONTAINER' -mindepth 1 -delete
    cp -a /tmp/attachments-restore-staging/. '$ATTACHMENTS_PATH_IN_CONTAINER'/
    rm -rf /tmp/attachments-restore-staging
  "; then
  die "attachment restore failed — if the failure was during extraction/validation, the attachments volume was not touched; if it was during the clear-and-copy step, the volume may be in a partial state. See output above before restarting backend/celery_worker."
fi

log "Restarting backend and celery_worker ..."
compose up -d backend celery_worker

log "Attachment restore complete. Run the post-restore verification checklist in docs/BACKUP_AND_RESTORE.md next."
