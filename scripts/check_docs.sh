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
#   3. No stray "bugfixer.example"/"bugfixer.com"-shaped domain remains.
#   4. No pre-rename placeholder repository URL (bitbucket-claude/aivah)
#      remains anywhere.
#   5. No leftover pre-rename branding remains outside the explicit
#      allowlist below (each entry with its own comment explaining why
#      it's still there).
#   6. No "REPLACE-ME" placeholder contact remains anywhere (the security and
#      Code of Conduct contacts are resolved, real addresses — see below),
#      and security@quorfix.com / conduct@quorfix.com appear in every file
#      that must document them.
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
  "github.com/mozilla/diversity"      # CODE_OF_CONDUCT.md's Contributor Covenant attribution link
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

# --- 5. No leftover pre-rename branding --------------------------------------
# Every file below is allowlisted with a reason — a NEW file matching the
# pattern that isn't in this list is what this check is meant to catch.

ALLOWED_BRANDING_FILES=(
  "scripts/check_docs.sh" # this script's own pattern-matching code/comments (checks 3 and 5)
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
[ "$unexpected_branding" -eq 1 ] || ok "no unallowlisted pre-rename branding reference remains"

# --- 6. Confirmed contacts present; no REPLACE-ME placeholder remains ------

replace_me_hits="$(git -C "$REPO_ROOT" grep -l 'REPLACE-ME' -- '*.md' '*.yml' 2>/dev/null || true)"
if [ -n "$replace_me_hits" ]; then
  fail "REPLACE-ME placeholder contact remains (should be fully resolved) in:"
  echo "$replace_me_hits" >&2
else
  ok "no REPLACE-ME placeholder contact remains anywhere"
fi

SECURITY_CONTACT_FILES=("docs/SECURITY.md" "README.md" ".github/ISSUE_TEMPLATE/config.yml")
missing_security_contact=0
for f in "${SECURITY_CONTACT_FILES[@]}"; do
  if ! grep -q 'security@quorfix\.com' "$REPO_ROOT/$f" 2>/dev/null; then
    fail "security@quorfix.com missing from: $f"
    missing_security_contact=1
  fi
done
[ "$missing_security_contact" -eq 1 ] || ok "security@quorfix.com present in every required file"

if grep -q 'conduct@quorfix\.com' "$REPO_ROOT/CODE_OF_CONDUCT.md" 2>/dev/null; then
  ok "conduct@quorfix.com present in CODE_OF_CONDUCT.md"
else
  fail "conduct@quorfix.com missing from: CODE_OF_CONDUCT.md"
fi

echo >&2
if [ "$FAIL" -eq 0 ]; then
  echo "Documentation check passed." >&2
else
  echo "Documentation check FAILED." >&2
fi
exit "$FAIL"
