#!/usr/bin/env bash
# Shared helpers for scripts/{backup,backup_db,backup_attachments,restore_db,
# restore_attachments}.sh. This file is a library — sourced, never executed
# directly, and never invoked with any Compose file other than the one the
# caller resolved via -f/-e.

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "scripts/lib/common.sh is a library — source it from another script, don't run it directly." >&2
  exit 1
fi

DEFAULT_COMPOSE_FILE="docker-compose.prod.yml"
DEFAULT_ENV_FILE=".env"

COMPOSE_FILE="${COMPOSE_FILE:-$DEFAULT_COMPOSE_FILE}"
ENV_FILE="${ENV_FILE:-$DEFAULT_ENV_FILE}"

log() { printf '%s\n' "$*" >&2; }
die() {
  log "error: $*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found on PATH: $1"
}

# Thin wrapper so every script targets the same resolved Compose/env file
# pair without repeating the flags at every call site.
compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

utc_timestamp() {
  date -u +%Y%m%dT%H%M%SZ
}

# Portable sha256: prefers sha256sum (GNU coreutils, most Linux distros —
# including the CI/dev environment this stack targets); falls back to
# `shasum -a 256` (macOS, BSD) so the scripts aren't Linux-only.
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$@"
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$@"
  else
    die "neither sha256sum nor shasum is available on PATH"
  fi
}

# Verifies every entry in a `sha256sum`-format checksum file (as produced by
# sha256_of / `sha256sum a b`), resolving relative paths against the
# checksum file's own directory so it can be run from any working
# directory. Exits nonzero (via die) on any mismatch or missing file.
verify_checksums() {
  checksums_file="$1"
  [ -f "$checksums_file" ] || die "checksum file not found: $checksums_file"
  checksums_dir="$(cd -- "$(dirname -- "$checksums_file")" >/dev/null 2>&1 && pwd)"
  sha_cmd=""
  if command -v sha256sum >/dev/null 2>&1; then
    sha_cmd="sha256sum"
  elif command -v shasum >/dev/null 2>&1; then
    sha_cmd="shasum -a 256"
  else
    die "neither sha256sum nor shasum is available on PATH"
  fi
  ( cd -- "$checksums_dir" && $sha_cmd -c "$(basename -- "$checksums_file")" ) \
    || die "checksum verification failed for one or more files listed in $checksums_file"
}

MANIFEST_FORMAT_VERSION=1

# Verifies a single named file against its entry in a sha256sum-format
# checksums file, without requiring every other file listed in that
# checksums file to also be present (unlike verify_checksums, which checks
# every entry). Used by the restore scripts, which each restore one
# artifact at a time.
verify_single_checksum() {
  checksums_file="$1"
  target_dir="$2"
  target_basename="$3"
  [ -f "$checksums_file" ] || die "checksum file not found: $checksums_file"
  line="$(grep -E "[[:space:]]\\*?${target_basename}\$" "$checksums_file" || true)"
  [ -n "$line" ] || die "$target_basename is not listed in $checksums_file"
  sha_cmd=""
  if command -v sha256sum >/dev/null 2>&1; then
    sha_cmd="sha256sum"
  elif command -v shasum >/dev/null 2>&1; then
    sha_cmd="shasum -a 256"
  else
    die "neither sha256sum nor shasum is available on PATH"
  fi
  single_entry_file="$(mktemp)"
  printf '%s\n' "$line" >"$single_entry_file"
  if ! (cd -- "$target_dir" && $sha_cmd -c "$single_entry_file" >/dev/null); then
    rm -f -- "$single_entry_file"
    die "checksum mismatch for $target_basename — refusing to restore an unverified artifact"
  fi
  rm -f -- "$single_entry_file"
}

# If a manifest.txt exists next to the artifact being restored, requires it
# to report a known format_version and status=complete. If no manifest.txt
# is present at all (e.g. a standalone file copied out of its recovery-set
# directory), this only warns — the checksum check above is mandatory
# either way, but the manifest gives an extra, independent guarantee that
# every step of the *original* backup actually succeeded.
require_manifest_complete_if_present() {
  manifest_file="$1"
  if [ ! -f "$manifest_file" ]; then
    log "warning: no manifest.txt found alongside this artifact — proceeding on checksum verification alone"
    return 0
  fi
  grep -q "^format_version=${MANIFEST_FORMAT_VERSION}\$" "$manifest_file" \
    || die "manifest.txt format_version is missing or does not match the expected value ($MANIFEST_FORMAT_VERSION) — refusing to restore"
  grep -q '^status=complete$' "$manifest_file" \
    || die "manifest.txt status is not 'complete' — this backup is incomplete or failed; refusing to restore"
}

# Validates a restore input file end to end: exists, non-empty, checksum
# matches checksums.sha256 in the same directory, and manifest.txt (if
# present in that directory) reports a complete backup of a known format.
require_verified_artifact() {
  artifact="$1"
  [ -f "$artifact" ] || die "input file not found: $artifact"
  [ -s "$artifact" ] || die "input file is empty: $artifact"
  artifact_dir="$(cd -- "$(dirname -- "$artifact")" >/dev/null 2>&1 && pwd)"
  artifact_base="$(basename -- "$artifact")"
  verify_single_checksum "${artifact_dir}/checksums.sha256" "$artifact_dir" "$artifact_base"
  require_manifest_complete_if_present "${artifact_dir}/manifest.txt"
}

require_confirm_flag() {
  # Usage: require_confirm_flag "$@" — dies unless --confirm-restore is
  # present verbatim among the arguments. Deliberately a single fixed
  # literal flag (not "-y", not a prompt) so a restore can never be
  # triggered by an accidental short flag or an unattended "yes" pipe.
  found=0
  for arg in "$@"; do
    if [ "$arg" = "--confirm-restore" ]; then
      found=1
    fi
  done
  [ "$found" -eq 1 ] || die "refusing to proceed without --confirm-restore (this operation is destructive)"
}

refuse_if_exists() {
  [ -e "$1" ] && die "refusing to overwrite existing path: $1"
  return 0
}
