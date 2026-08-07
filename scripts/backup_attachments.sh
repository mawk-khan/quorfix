#!/usr/bin/env bash
# scripts/backup_attachments.sh — local-attachments backup for Quorfix's
# production Compose stack (docker-compose.prod.yml's `attachments_data`
# named volume, mounted at ATTACHMENTS_LOCAL_ROOT in the `backend` and
# `celery_worker` services).
#
# Usage:
#   scripts/backup_attachments.sh [-f COMPOSE_FILE] [-e ENV_FILE] <output-file>
#
# Writes a gzip-compressed tar archive of the attachment volume's contents
# to <output-file>, produced by a disposable, no-dependency run of the
# already-built backend image itself (`docker compose run --rm --no-deps`)
# — no separate helper image is pulled, and no host-specific volume mount
# path is assumed: the exact volume/path declared in COMPOSE_FILE is
# reused as-is. The container's own ENTRYPOINT is bypassed (--entrypoint
# "") so this plain filesystem operation never depends on the full Django
# production system checks passing.
#
# See docs/BACKUP_AND_RESTORE.md for the full procedure.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

# Must match ATTACHMENTS_LOCAL_ROOT as set on the `backend`/`celery_worker`
# services in docker-compose.prod.yml.
ATTACHMENTS_PATH_IN_CONTAINER="/data/attachments"

usage() {
  cat >&2 <<USAGE
Usage: $(basename "$0") [-f COMPOSE_FILE] [-e ENV_FILE] <output-file>

  -f COMPOSE_FILE   Compose file to use (default: $DEFAULT_COMPOSE_FILE)
  -e ENV_FILE       Env file passed as --env-file (default: $DEFAULT_ENV_FILE)
  <output-file>     Path to write the attachments.tar.gz archive to.
                     Must not already exist.
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
OUTPUT_FILE="$1"

refuse_if_exists "$OUTPUT_FILE"
require_cmd docker
require_cmd tar
[ -f "$COMPOSE_FILE" ] || die "compose file not found: $COMPOSE_FILE"

case "$OUTPUT_FILE" in
  /*) OUTPUT_ABS="$OUTPUT_FILE" ;;
  *) OUTPUT_ABS="$(pwd)/$OUTPUT_FILE" ;;
esac
OUTPUT_DIR="$(dirname -- "$OUTPUT_ABS")"
OUTPUT_BASENAME="$(basename -- "$OUTPUT_ABS")"
[ -d "$OUTPUT_DIR" ] || die "output directory does not exist: $OUTPUT_DIR"
TMP_BASENAME="${OUTPUT_BASENAME}.tmp.$$"

cleanup() {
  rm -f -- "${OUTPUT_DIR}/${TMP_BASENAME}"
}
trap cleanup EXIT INT TERM

log "Backing up attachments via '$COMPOSE_FILE' service 'backend' ($ATTACHMENTS_PATH_IN_CONTAINER) -> $OUTPUT_FILE"

# Bind-mount the host output directory at /backup so the container writes
# the archive directly to its final location (still under a .tmp name, for
# atomicity) — no intermediate copy through the host is needed. `-C
# "$ATTACHMENTS_PATH_IN_CONTAINER" .` records members relative to the
# attachments root (e.g. "./sub/file.bin"), never as absolute paths, and
# tar with a plain directory source never follows a path outside that root
# on its own; restore_attachments.sh independently re-validates every
# member before extraction regardless.
if ! compose run --rm --no-deps --entrypoint "" \
  -v "${OUTPUT_DIR}:/backup" \
  backend \
  tar czf "/backup/${TMP_BASENAME}" -C "$ATTACHMENTS_PATH_IN_CONTAINER" .; then
  die "tar failed while archiving attachments. No output file was written."
fi

[ -s "${OUTPUT_DIR}/${TMP_BASENAME}" ] || die "attachment archive is empty on disk — tar did not produce output."

log "Verifying archive can be listed ..."
if ! tar tzf "${OUTPUT_DIR}/${TMP_BASENAME}" >/dev/null; then
  die "tar tzf could not list the archive — the backup did not verify."
fi

mv -- "${OUTPUT_DIR}/${TMP_BASENAME}" "$OUTPUT_ABS"
chmod 600 "$OUTPUT_ABS"
trap - EXIT INT TERM

log "Attachment backup verified and written: $OUTPUT_FILE"
printf '%s\n' "$OUTPUT_FILE"
