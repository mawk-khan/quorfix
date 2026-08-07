#!/usr/bin/env bash
# scripts/backup_db.sh — PostgreSQL backup for Quorfix's production
# Compose stack (docker-compose.prod.yml's `db` service).
#
# Usage:
#   scripts/backup_db.sh [-f COMPOSE_FILE] [-e ENV_FILE] <output-file>
#
# Writes a pg_dump custom-format archive (schema + data, including
# migration records — not a plain-SQL dump) to <output-file>, using the
# pg_dump/pg_restore binaries already present in the running `db`
# container, not a host-installed PostgreSQL client. POSTGRES_USER/
# POSTGRES_DB are read from that container's own environment (as set by
# docker-compose.prod.yml from ENV_FILE) — this script never reads, needs,
# or prints POSTGRES_PASSWORD: `docker compose exec` connects over the
# container's local Unix socket, which the official postgres image trusts
# locally by default (see docs/BACKUP_AND_RESTORE.md for why this is safe).
#
# Ordinary use does not stop the backend/celery_worker services — pg_dump
# takes a consistent MVCC snapshot without blocking concurrent writers.
#
# See docs/BACKUP_AND_RESTORE.md for the full procedure and its
# consistency limitations relative to the attachments backup.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat >&2 <<USAGE
Usage: $(basename "$0") [-f COMPOSE_FILE] [-e ENV_FILE] <output-file>

  -f COMPOSE_FILE   Compose file to use (default: $DEFAULT_COMPOSE_FILE)
  -e ENV_FILE       Env file passed as --env-file (default: $DEFAULT_ENV_FILE)
  <output-file>     Path to write the pg_dump custom-format archive to.
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
[ -f "$COMPOSE_FILE" ] || die "compose file not found: $COMPOSE_FILE"

TMP_FILE="${OUTPUT_FILE}.tmp.$$"
cleanup() {
  rm -f -- "$TMP_FILE"
}
trap cleanup EXIT INT TERM

log "Backing up database via '$COMPOSE_FILE' service 'db' -> $OUTPUT_FILE"

# --format=custom is the primary, documented format: it supports the
# pg_restore --list verification below, selective/parallel restore, and
# --clean --if-exists at restore time — a plain-SQL dump supports none of
# that. --compress=6 is a moderate zlib level accepted by pg_dump on every
# PostgreSQL version this stack targets (16).
if ! compose exec -T db sh -c \
  'pg_dump --format=custom --compress=6 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' \
  >"$TMP_FILE"; then
  die "pg_dump failed — see output above. No output file was written."
fi

[ -s "$TMP_FILE" ] || die "pg_dump produced an empty file — refusing to treat this as a valid backup."

log "Verifying dump with pg_restore --list ..."
if ! compose exec -T db pg_restore --list <"$TMP_FILE" >/dev/null; then
  die "pg_restore --list could not read the dump — the backup did not verify. No output file was kept."
fi

mv -- "$TMP_FILE" "$OUTPUT_FILE"
chmod 600 "$OUTPUT_FILE"
trap - EXIT INT TERM

log "Database backup verified and written: $OUTPUT_FILE"
printf '%s\n' "$OUTPUT_FILE"
