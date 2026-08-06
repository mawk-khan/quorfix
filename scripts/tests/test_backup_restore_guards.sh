#!/usr/bin/env bash
# scripts/tests/test_backup_restore_guards.sh — fast tests for the
# backup/restore scripts' guard clauses: overwrite refusal, the
# --confirm-restore requirement, and checksum/manifest validation. These
# are exactly the checks each script performs *before* touching a Docker
# daemon (`docker` only needs to be on PATH — see require_cmd in
# scripts/lib/common.sh), so this suite runs the same with or without a
# running Docker daemon and never touches any real database or volume.
#
# Docker-daemon-dependent behavior (pg_dump/pg_restore against a real
# database, tar against a real attachments volume, a full live restore) is
# covered instead by the end-to-end disposable restore drill — see
# "Full restore procedure" in docs/BACKUP_AND_RESTORE.md.
#
# Run: scripts/tests/test_backup_restore_guards.sh

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
SCRIPTS_DIR="$(cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)"

PASS=0
FAIL=0

assert_nonzero() {
  desc="$1"
  shift
  out="$("$@" 2>&1)"
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $desc (expected nonzero exit, got 0)"
    printf '%s\n' "$out"
    FAIL=$((FAIL + 1))
  fi
}

assert_output_contains() {
  desc="$1"
  needle="$2"
  shift 2
  out="$("$@" 2>&1)"
  if printf '%s' "$out" | grep -qF -- "$needle"; then
    echo "PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $desc (expected output to contain: $needle)"
    printf '%s\n' "$out"
    FAIL=$((FAIL + 1))
  fi
}

assert_output_not_contains() {
  desc="$1"
  needle="$2"
  shift 2
  out="$("$@" 2>&1)"
  if printf '%s' "$out" | grep -qF -- "$needle"; then
    echo "FAIL: $desc (did not expect output to contain: $needle)"
    printf '%s\n' "$out"
    FAIL=$((FAIL + 1))
  else
    echo "PASS: $desc"
    PASS=$((PASS + 1))
  fi
}

sha256_line_for() {
  # Writes a valid sha256sum-format line for $1 (a file) to stdout.
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1"
  else
    shasum -a 256 "$1"
  fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- backup_db.sh / backup_attachments.sh: refuse to overwrite -----------

touch "$TMP/existing-db.dump"
assert_nonzero "backup_db.sh refuses to overwrite an existing output file" \
  "$SCRIPTS_DIR/backup_db.sh" "$TMP/existing-db.dump"

touch "$TMP/existing-attachments.tar.gz"
assert_nonzero "backup_attachments.sh refuses to overwrite an existing output file" \
  "$SCRIPTS_DIR/backup_attachments.sh" "$TMP/existing-attachments.tar.gz"

# backup.sh's own recovery-set-directory overwrite refusal
# (bugfixer-backup-<UTC timestamp>/) is timestamp-keyed, so it can't be
# collided with deterministically from outside without controlling the
# clock — it's exercised for real as part of the end-to-end disposable
# restore drill instead (see docs/BACKUP_AND_RESTORE.md). The two refusals
# above already cover the same underlying refuse_if_exists() helper
# directly.

# --- backup.sh: refuse to write inside the repository ---------------------

REPO_ROOT="$(cd -- "$SCRIPTS_DIR/.." >/dev/null 2>&1 && pwd)"
assert_nonzero "backup.sh refuses a destination inside the repository" \
  "$SCRIPTS_DIR/backup.sh" "$REPO_ROOT"

# --- restore_db.sh / restore_attachments.sh: require --confirm-restore ---

touch "$TMP/some.dump"
assert_nonzero "restore_db.sh refuses to run without --confirm-restore" \
  "$SCRIPTS_DIR/restore_db.sh" "$TMP/some.dump"

touch "$TMP/some.tar.gz"
assert_nonzero "restore_attachments.sh refuses to run without --confirm-restore" \
  "$SCRIPTS_DIR/restore_attachments.sh" "$TMP/some.tar.gz"

# --- missing checksums.sha256 blocks restore ------------------------------

NOCKDIR="$TMP/no-checksum"
mkdir -p "$NOCKDIR"
printf 'fake dump content\n' >"$NOCKDIR/database.dump"
assert_nonzero "restore_db.sh refuses when no checksums.sha256 is present" \
  "$SCRIPTS_DIR/restore_db.sh" --confirm-restore "$NOCKDIR/database.dump"

# --- checksum mismatch blocks restore -------------------------------------

CKDIR="$TMP/checksum-mismatch"
mkdir -p "$CKDIR"
printf 'fake dump content\n' >"$CKDIR/database.dump"
printf '0000000000000000000000000000000000000000000000000000000000000000  database.dump\n' >"$CKDIR/checksums.sha256"
assert_nonzero "restore_db.sh refuses on checksum mismatch" \
  "$SCRIPTS_DIR/restore_db.sh" --confirm-restore "$CKDIR/database.dump"

ACKDIR="$TMP/checksum-mismatch-attachments"
mkdir -p "$ACKDIR"
printf 'fake tar content\n' >"$ACKDIR/attachments.tar.gz"
printf '0000000000000000000000000000000000000000000000000000000000000000  attachments.tar.gz\n' >"$ACKDIR/checksums.sha256"
assert_nonzero "restore_attachments.sh refuses on checksum mismatch" \
  "$SCRIPTS_DIR/restore_attachments.sh" --confirm-restore "$ACKDIR/attachments.tar.gz"

# --- incomplete manifest blocks restore -----------------------------------

INCDIR="$TMP/incomplete-manifest"
mkdir -p "$INCDIR"
printf 'fake dump content\n' >"$INCDIR/database.dump"
(cd "$INCDIR" && sha256_line_for database.dump) >"$INCDIR/checksums.sha256"
cat >"$INCDIR/manifest.txt" <<'EOF'
format_version=1
status=in_progress
EOF
assert_nonzero "restore_db.sh refuses when manifest.txt status is not complete" \
  "$SCRIPTS_DIR/restore_db.sh" --confirm-restore "$INCDIR/database.dump"

# --- wrong format version blocks restore ----------------------------------

WRONGVERDIR="$TMP/wrong-format-version"
mkdir -p "$WRONGVERDIR"
printf 'fake dump content\n' >"$WRONGVERDIR/database.dump"
(cd "$WRONGVERDIR" && sha256_line_for database.dump) >"$WRONGVERDIR/checksums.sha256"
cat >"$WRONGVERDIR/manifest.txt" <<'EOF'
format_version=99
status=complete
EOF
assert_nonzero "restore_db.sh refuses when manifest.txt format_version does not match" \
  "$SCRIPTS_DIR/restore_db.sh" --confirm-restore "$WRONGVERDIR/database.dump"

# --- a genuinely valid checksum + complete manifest passes validation -----
# (it still fails later, at the nonexistent Compose file below — that's
# the point: this proves validation itself accepts a valid input rather
# than rejecting everything indiscriminately, without needing a live
# Docker daemon to get all the way through a real restore.)

VALIDDIR="$TMP/valid-manifest"
mkdir -p "$VALIDDIR"
printf 'fake dump content\n' >"$VALIDDIR/database.dump"
(cd "$VALIDDIR" && sha256_line_for database.dump) >"$VALIDDIR/checksums.sha256"
cat >"$VALIDDIR/manifest.txt" <<'EOF'
format_version=1
status=complete
EOF
assert_output_contains "restore_db.sh: nonexistent compose file is the failure reason for a valid input" \
  "compose file not found" \
  "$SCRIPTS_DIR/restore_db.sh" -f "$TMP/does-not-exist-compose.yml" --confirm-restore "$VALIDDIR/database.dump"
assert_output_not_contains "restore_db.sh: a valid input never fails on checksum mismatch" \
  "checksum mismatch" \
  "$SCRIPTS_DIR/restore_db.sh" -f "$TMP/does-not-exist-compose.yml" --confirm-restore "$VALIDDIR/database.dump"
assert_output_not_contains "restore_db.sh: a valid input never fails on manifest status" \
  "status is not 'complete'" \
  "$SCRIPTS_DIR/restore_db.sh" -f "$TMP/does-not-exist-compose.yml" --confirm-restore "$VALIDDIR/database.dump"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
