#!/usr/bin/env bash
# scripts/check_docs.sh — lightweight documentation/branding validation.
# Read-only: never modifies anything. See docs/RELEASING.md's pre-release
# checklist, which runs this.
#
# Checks:
#   1. Every relative Markdown link in a tracked *.md file resolves to a
#      real file on disk.
#   2. Every github.com link points at github.com/mawk-khan/quorfix, unless
#      explicitly allowlisted below (with a reason).
#   3. No stray "bugfixer.example"/"bugfixer.com"-shaped domain remains
#      (the one intentionally-retained domain, "bugfixer.local" demo
#      emails, is allowlisted below).
#   4. No pre-rename placeholder repository URL (bitbucket-claude/aivah)
#      remains anywhere.
#   5. No unintended old "Bug Fixer" branding remains outside the explicit
#      allowlist (established environment variables, legacy demo/backup
#      identifiers kept for compatibility — each with its own comment
#      explaining why it's still there).
#   6. Every "REPLACE-ME" placeholder found is one of the two expected,
#      already-tracked release blockers (docs/SECURITY.md,
#      CODE_OF_CONDUCT.md) — not a leftover somewhere else.
#
# Deliberately does NOT fail on a historical Git commit subject quoted
# verbatim in documentation (this script never inspects `git log` output at
# all, so there's nothing to exempt there in practice).
#
# Usage: scripts/check_docs.sh

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)"
cd -- "$REPO_ROOT"

FAIL=0
fail() {
  echo "FAIL: $*" >&2
  FAIL=1
}
ok() { echo "OK: $*" >&2; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: required command not found on PATH: $1" >&2
    exit 1
  }
}
require_cmd git
require_cmd python3

# Only tracked files — never scans .git/, node_modules/, .venv/, or any
# other untracked/generated content.
mapfile -t MD_FILES < <(git -C "$REPO_ROOT" ls-files -- '*.md')

# --- 1. Relative Markdown links resolve ------------------------------------

python3 - "$REPO_ROOT" "${MD_FILES[@]}" <<'PYEOF'
import re
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
files = sys.argv[2:]
link_re = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
fenced_code_re = re.compile(r"```.*?```", re.DOTALL)
inline_code_re = re.compile(r"`[^`\n]*`")
failures = []

for rel in files:
    path = repo_root / rel
    raw_text = path.read_text(errors="replace")
    # Blank out fenced and inline code (replace with equal-length spaces so
    # match positions/line numbers stay meaningful) — a mention-syntax
    # example like `@[Name](mention:<uuid>)` in backticks is documentation
    # of app syntax, not a real relative link, and must never be checked
    # as one.
    text = fenced_code_re.sub(lambda m: " " * len(m.group(0)), raw_text)
    text = inline_code_re.sub(lambda m: " " * len(m.group(0)), text)
    for match in link_re.finditer(text):
        target = match.group(1).strip()
        if not target:
            continue
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        target = target.split("#", 1)[0].strip()
        if not target:
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(repo_root.resolve())
        except ValueError:
            pass  # outside the repo entirely — let the exists() check below judge it
        if not resolved.exists():
            failures.append(f"{rel}: broken relative link -> {target}")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    sys.exit(1)
print("OK: every relative Markdown link resolves")
PYEOF
[ "$?" -eq 0 ] || FAIL=1

# --- 2. GitHub links point at mawk-khan/quorfix -----------------------------

# Allowlisted github.com prefixes that are NOT this repository — each is a
# legitimate third-party reference, not a leftover placeholder.
ALLOWED_GITHUB_PREFIXES=(
  "github.com/mawk-khan/quorfix"      # this repository — the only "our own" one
  "github.com/sponsors/"              # npm package funding links (package-lock.json)
  "github.com/Masterminds/semver"     # .ddev/config.yaml's own boilerplate comment
  "github.com/chalk/"                 # npm package funding links
  "github.com/fb55/"                  # npm package funding links
  "github.com/inikulin/"              # npm package funding links
  "github.com/privatenumber/"         # npm package funding links
  "github.com/vitejs/vite"            # npm package funding link
)

github_hits="$(git -C "$REPO_ROOT" grep -noE 'github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+' -- '*.md' '*.yml' '*.json' 2>/dev/null || true)"
if [ -n "$github_hits" ]; then
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    url_part="${line#*:*:}"
    allowed=0
    for prefix in "${ALLOWED_GITHUB_PREFIXES[@]}"; do
      case "$url_part" in
        "$prefix"*) allowed=1 ;;
      esac
    done
    if [ "$allowed" -eq 0 ]; then
      fail "unrecognized GitHub reference (not mawk-khan/quorfix, not allowlisted): $line"
    fi
  done <<<"$github_hits"
fi
[ "$FAIL" -eq 1 ] || ok "every github.com reference points at mawk-khan/quorfix or an allowlisted third party"

# --- 3. No stray bugfixer.example/bugfixer.com domain -----------------------
# bugfixer.local (demo emails) is the one intentionally-retained domain —
# see seed_demo.py's own comment for why.

stray_domain="$(git -C "$REPO_ROOT" grep -noE 'bugfixer\.(example|com|dev|io|net|org)' -- '*.md' '*.yml' 2>/dev/null || true)"
if [ -n "$stray_domain" ]; then
  fail "stray non-quorfix.com domain reference(s) found:"
  echo "$stray_domain" >&2
else
  ok "no stray bugfixer.example/.com-shaped domain reference"
fi

# --- 4. No pre-rename placeholder repository URL ----------------------------

old_repo="$(git -C "$REPO_ROOT" grep -noE 'bitbucket-claude|aivah/bug-fixer' -- '*.md' '*.yml' 'Dockerfile' '**/Dockerfile' 2>/dev/null || true)"
if [ -n "$old_repo" ]; then
  fail "pre-rename placeholder repository reference(s) found:"
  echo "$old_repo" >&2
else
  ok "no pre-rename placeholder repository URL remains"
fi

# --- 5. No unintended old "Bug Fixer" branding ------------------------------
# Every file below is allowlisted with a reason — a NEW file matching the
# pattern that isn't in this list is what this check is meant to catch.

ALLOWED_BRANDING_FILES=(
  ".gitignore"                                                     # legacy backup-prefix gitignore pattern, kept for compatibility
  "Makefile"                                                       # BUGFIXER_DISPOSABLE_DATABASE — established env var, kept per CLAUDE.md Chunk K policy
  "backend/apps/core/management/commands/generate_perf_dataset.py" # BUGFIXER_DISPOSABLE_DATABASE + legacy demo slug guard
  "backend/apps/core/management/commands/measure_performance.py"   # BUGFIXER_DISPOSABLE_DATABASE reference
  "backend/apps/core/management/commands/seed_demo.py"             # LEGACY_DEMO_ORG_SLUG + bugfixer.local demo emails, both intentional
  "backend/apps/core/tests/test_generate_perf_dataset.py"          # tests the legacy-slug guard above
  "backend/apps/core/tests/test_measure_performance.py"            # BUGFIXER_DISPOSABLE_DATABASE reference
  "backend/apps/core/tests/test_seed_demo.py"                      # tests bugfixer.local emails + legacy-org reuse
  "docker-compose.yml"                                             # Compose project name deliberately unrenamed (live local dev data)
  "docs/ACCESS_AND_TESTING.md"                                     # documents legacy demo email + historical Chunk G entry
  "docs/BACKUP_AND_RESTORE.md"                                     # documents legacy backup-prefix compatibility
  "docs/PERFORMANCE.md"                                            # references docker-compose.yml's own unrenamed network name
  "scripts/backup.sh"                                              # naming-compatibility comment
  "scripts/tests/test_backup_restore_guards.sh"                    # legacy-prefix regression test
  "CHANGELOG.md"                                                   # describes the branding migration itself
)

is_allowlisted_branding_file() {
  local f="$1"
  for allowed in "${ALLOWED_BRANDING_FILES[@]}"; do
    [ "$f" = "$allowed" ] && return 0
  done
  return 1
}

branding_hits="$(git -C "$REPO_ROOT" grep -lliE 'bug[ _-]?fixer' -- '*.md' '*.py' '*.ts' '*.tsx' '*.yml' '*.sh' 2>/dev/null || true)"
unexpected_branding=0
if [ -n "$branding_hits" ]; then
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    if ! is_allowlisted_branding_file "$f"; then
      fail "unexpected old branding reference in: $f (not on the allowlist — add it with a reason, or fix the reference)"
      unexpected_branding=1
    fi
  done <<<"$branding_hits"
fi
[ "$unexpected_branding" -eq 1 ] || ok "no unallowlisted old \"Bug Fixer\" branding reference remains"

# --- 6. Every REPLACE-ME placeholder is one of the two expected ones -------

replace_me_hits="$(git -C "$REPO_ROOT" grep -l 'REPLACE-ME' -- '*.md' 2>/dev/null || true)"
EXPECTED_PLACEHOLDER_FILES=("docs/SECURITY.md" "CODE_OF_CONDUCT.md" "docs/ACCESS_AND_TESTING.md")
unexpected_placeholder=0
if [ -n "$replace_me_hits" ]; then
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    found=0
    for expected in "${EXPECTED_PLACEHOLDER_FILES[@]}"; do
      [ "$f" = "$expected" ] && found=1
    done
    if [ "$found" -eq 0 ]; then
      fail "unexpected REPLACE-ME placeholder in: $f"
      unexpected_placeholder=1
    fi
  done <<<"$replace_me_hits"
fi
[ "$unexpected_placeholder" -eq 1 ] || ok "REPLACE-ME placeholders only appear in the expected, tracked files"

for f in "${EXPECTED_PLACEHOLDER_FILES[@]}"; do
  if ! grep -q 'REPLACE-ME' "$REPO_ROOT/$f" 2>/dev/null; then
    echo "INFO: $f no longer contains a REPLACE-ME placeholder — if the contact was genuinely" >&2
    echo "      configured and verified, update docs/RELEASING.md's checklist accordingly;" >&2
    echo "      if this was accidental, the release blocker may have been silently dropped." >&2
  fi
done

echo >&2
if [ "$FAIL" -eq 0 ]; then
  echo "Documentation check passed." >&2
else
  echo "Documentation check FAILED." >&2
fi
exit "$FAIL"
