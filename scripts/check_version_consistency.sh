#!/usr/bin/env bash
# scripts/check_version_consistency.sh — verifies the root VERSION file (the
# single source of truth — see docs/RELEASING.md) is well-formed and that
# every place expected to mention it actually agrees with it:
#   - VERSION itself is a valid semver value, with an optional prerelease
#     suffix (X.Y.Z or X.Y.Z-prerelease.N).
#   - CHANGELOG.md has a matching version heading.
#   - If the current commit is tagged, the tag equals v<VERSION> (informational
#     only when untagged — this repository has not cut a release yet, so an
#     untagged working tree is the normal, expected state, not a failure).
#
# Read-only: never modifies VERSION, CHANGELOG.md, or any tag. Intended to
# run locally before tagging a release (see docs/RELEASING.md) and as part
# of local pre-release verification; .github/workflows/release.yml enforces
# the tag == v<VERSION> equality itself, independently, at release time.
#
# Usage: scripts/check_version_consistency.sh

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)"

log() { printf '%s\n' "$*" >&2; }
FAIL=0
fail() {
  log "FAIL: $*"
  FAIL=1
}
ok() { log "OK: $*"; }

VERSION_FILE="$REPO_ROOT/VERSION"
[ -f "$VERSION_FILE" ] || {
  log "FAIL: VERSION file not found at $VERSION_FILE"
  exit 1
}

VERSION_CONTENT="$(tr -d '[:space:]' <"$VERSION_FILE")"

SEMVER_RE='^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$'
if [[ "$VERSION_CONTENT" =~ $SEMVER_RE ]]; then
  ok "VERSION ('$VERSION_CONTENT') is a well-formed semantic version"
else
  fail "VERSION ('$VERSION_CONTENT') is not a well-formed X.Y.Z or X.Y.Z-prerelease value"
fi

CHANGELOG="$REPO_ROOT/CHANGELOG.md"
if [ -f "$CHANGELOG" ]; then
  if grep -qE "^## \[?${VERSION_CONTENT//./\\.}\]?" "$CHANGELOG"; then
    ok "CHANGELOG.md has a heading matching VERSION ('$VERSION_CONTENT')"
  else
    fail "CHANGELOG.md has no heading matching VERSION ('$VERSION_CONTENT') — add one before tagging a release"
  fi
else
  fail "CHANGELOG.md not found at $CHANGELOG"
fi

if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  CURRENT_TAG="$(git -C "$REPO_ROOT" describe --tags --exact-match 2>/dev/null || true)"
  if [ -n "$CURRENT_TAG" ]; then
    if [ "$CURRENT_TAG" = "v${VERSION_CONTENT}" ]; then
      ok "current commit's tag ('$CURRENT_TAG') matches v<VERSION>"
    else
      fail "current commit's tag ('$CURRENT_TAG') does not equal v${VERSION_CONTENT} — update VERSION or the tag"
    fi
  else
    log "INFO: current commit is not tagged — expected pre-release; see .github/workflows/release.yml for the enforced check at actual release time"
  fi
fi

if [ "$FAIL" -eq 0 ]; then
  log "Version consistency check passed."
else
  log "Version consistency check FAILED."
fi
exit "$FAIL"
