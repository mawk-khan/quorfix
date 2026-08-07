#!/usr/bin/env bash
# scripts/inspect_version.sh — prints the OCI image labels baked into the
# locally built backend/frontend production images by their Dockerfiles'
# VERSION/VCS_REF build args (see "Build metadata" in backend/Dockerfile
# and frontend/Dockerfile). Read-only: never builds, pulls, starts, or
# stops anything. See docs/UPGRADING.md "Version metadata".
#
# Usage:
#   scripts/inspect_version.sh [IMAGE_TAG]
#
# IMAGE_TAG defaults to the VERSION environment variable if set, otherwise
# the repo's own root VERSION file (the single source of truth — see
# docs/RELEASING.md), otherwise "local" — matching docker-compose.prod.yml's
# own quorfix-backend:${VERSION:-local} / quorfix-frontend:${VERSION:-local}
# image tags, so `VERSION=1.2.3 scripts/inspect_version.sh` inspects exactly
# the images that VERSION would build/run, and a bare invocation with no
# VERSION env var set inspects exactly what `make prod-build` (which reads
# the same file) would have produced.
#
# A missing image or a missing label is reported, not treated as an error
# that aborts the whole check — each is independent, and the exit code
# reflects whether *both* images were found and readable.

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

require_cmd docker

VERSION_FILE_CONTENT="$(cat "$REPO_ROOT/VERSION" 2>/dev/null || true)"
TAG="${1:-${VERSION:-${VERSION_FILE_CONTENT:-local}}}"

print_labels() {
  image="$1"
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "$image: image not found locally (build it first, e.g. \`make prod-build\`)"
    return 1
  fi
  version_label="$(docker inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.version"}}' 2>/dev/null)"
  revision_label="$(docker inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' 2>/dev/null)"
  source_label="$(docker inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.source"}}' 2>/dev/null)"
  digest="$(docker inspect "$image" --format '{{.Id}}' 2>/dev/null)"
  [ -n "$version_label" ] || version_label="(no version label — built without the VERSION build arg)"
  [ -n "$revision_label" ] || revision_label="(no revision label — built without the VCS_REF build arg)"
  [ -n "$source_label" ] || source_label="(no source label)"
  printf '%s:\n  version:  %s\n  revision: %s\n  source:   %s\n  digest:   %s\n' \
    "$image" "$version_label" "$revision_label" "$source_label" "$digest"
}

status=0
print_labels "quorfix-backend:${TAG}" || status=1
print_labels "quorfix-frontend:${TAG}" || status=1
exit "$status"
