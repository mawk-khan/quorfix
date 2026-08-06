#!/usr/bin/env bash
# scripts/tests/test_upgrade_guards.sh — fast tests for the upgrade
# helpers' guard clauses and for the "no check command ever applies a
# migration" invariant. Docker-daemon-free (only `docker` needs to be on
# PATH — see require_cmd in scripts/lib/common.sh); a full live upgrade is
# covered by the disposable upgrade drill instead — see docs/UPGRADING.md.
#
# Run: scripts/tests/test_upgrade_guards.sh

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
SCRIPTS_DIR="$(cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "$SCRIPTS_DIR/.." >/dev/null 2>&1 && pwd)"

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

_extract_makefile_target() {
  # Prints just one Makefile target's recipe block (from "name:" up to, but
  # not including, the next top-level "word:" line).
  target="$1"
  file="$2"
  awk -v t="^${target}:" '
    $0 ~ t { flag=1; print; next }
    flag && /^[A-Za-z0-9._-]+:/ { flag=0 }
    flag { print }
  ' "$file"
}

assert_block_lacks_unguarded_migrate() {
  # Fails if the given block of text invokes `manage.py migrate` in a form
  # that would actually apply migrations — i.e. without --check, --plan,
  # or --dry-run on the same line. A bare grep for "migrate" would
  # false-positive on `migrate --check` itself, so this specifically
  # rejects "migrate" occurrences not immediately followed by one of those
  # flags on the same line.
  desc="$1"
  block="$2"
  offending="$(printf '%s\n' "$block" | grep -nE 'manage\.py[[:space:]]+migrate([[:space:]]|$)' \
    | grep -vE -- '--check|--plan|--dry-run' || true)"
  if [ -z "$offending" ]; then
    echo "PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $desc (found an unguarded migrate invocation):"
    printf '%s\n' "$offending"
    FAIL=$((FAIL + 1))
  fi
}

assert_file_lacks_unguarded_migrate() {
  desc="$1"
  file="$2"
  if [ ! -f "$file" ]; then
    echo "FAIL: $desc (file not found: $file)"
    FAIL=$((FAIL + 1))
    return
  fi
  assert_block_lacks_unguarded_migrate "$desc" "$(cat "$file")"
}

assert_contains() {
  desc="$1"
  file="$2"
  needle="$3"
  if [ -f "$file" ] && grep -qF -- "$needle" "$file"; then
    echo "PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $desc (expected $file to contain: $needle)"
    FAIL=$((FAIL + 1))
  fi
}

# --- upgrade_smoke.sh: refuses a missing Compose file ---------------------

assert_nonzero "upgrade_smoke.sh refuses a missing Compose file" \
  "$SCRIPTS_DIR/upgrade_smoke.sh" -f /tmp/does-not-exist-compose.yml

# --- inspect_version.sh: handles a missing image/labels gracefully --------

assert_nonzero "inspect_version.sh returns nonzero for a tag with no built image" \
  "$SCRIPTS_DIR/inspect_version.sh" "no-such-tag-ever-built-xyz"

# --- static: no "check"/"plan" command ever applies a migration -----------
# Scoped to each specific target's own recipe block, not the whole
# Makefile — prod-migrate's recipe is *supposed* to be a real, unguarded
# `manage.py migrate` (the explicit apply step), so a whole-file check
# would wrongly flag it.

for target in prod-migrations-check prod-migrations-plan prod-upgrade-check; do
  block="$(_extract_makefile_target "$target" "$REPO_ROOT/Makefile")"
  if [ -z "$block" ]; then
    echo "FAIL: Makefile target '$target' exists"
    FAIL=$((FAIL + 1))
    continue
  fi
  assert_block_lacks_unguarded_migrate \
    "Makefile target '$target' never calls an unguarded 'manage.py migrate'" "$block"
done

assert_file_lacks_unguarded_migrate \
  "upgrade_smoke.sh never calls an unguarded 'manage.py migrate'" \
  "$SCRIPTS_DIR/upgrade_smoke.sh"

# prod-migrate's recipe IS supposed to be a real, unguarded migrate — the
# explicit, separate apply step. Confirm it exists (a positive check, not
# the negative one above) so this test suite would fail loudly if that
# target were ever accidentally removed rather than just guarded.
assert_contains "Makefile still has an explicit, real prod-migrate target" \
  "$REPO_ROOT/Makefile" "python manage.py migrate"

# --- static: rollback docs reference backup restore for uncertain/every-
# migration-by-default cases, not just an abstract promise -----------------

assert_contains "docs/UPGRADING.md's rollback tree references restore_db.sh --confirm-restore" \
  "$REPO_ROOT/docs/UPGRADING.md" "scripts/restore_db.sh --confirm-restore"
assert_contains "docs/UPGRADING.md's rollback tree references restore_attachments.sh --confirm-restore" \
  "$REPO_ROOT/docs/UPGRADING.md" "scripts/restore_attachments.sh --confirm-restore"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
