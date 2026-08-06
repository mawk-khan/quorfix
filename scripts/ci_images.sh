#!/usr/bin/env bash
# scripts/ci_images.sh — runs the exact production image validation
# sequence (.github/workflows/images.yml) locally: builds both production
# images, verifies non-root runtime users, and runs the minimal container
# smoke check. Builds only — never pushes anywhere.
#
# Usage: scripts/ci_images.sh

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)"
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

require_cmd docker
require_cmd git

GIT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
VERSION="${GIT_SHA:0:12}"

log "Building backend production image ..."
docker build --build-arg VERSION="$VERSION" --build-arg VCS_REF="$GIT_SHA" \
  -t bugfixer-backend:ci "$REPO_ROOT/backend"

log "Building frontend production image ..."
docker build --build-arg VERSION="$VERSION" --build-arg VCS_REF="$GIT_SHA" \
  --build-arg BACKEND_INTERNAL_URL=http://backend:8000 \
  -t bugfixer-frontend:ci "$REPO_ROOT/frontend"

log "Image metadata:"
for image in bugfixer-backend:ci bugfixer-frontend:ci; do
  version_label="$(docker inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.version"}}')"
  revision_label="$(docker inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
  digest="$(docker inspect "$image" --format '{{.Id}}')"
  log "  $image  version=$version_label  revision=$revision_label  digest=$digest"
done

log "Verifying runtime users are non-root ..."
backend_uid="$(docker run --rm --entrypoint id bugfixer-backend:ci -u)"
[ "$backend_uid" -ne 0 ] || die "backend image runs as root (uid 0)"
log "  backend uid: $backend_uid"

frontend_uid="$(docker run --rm --entrypoint id bugfixer-frontend:ci -u)"
[ "$frontend_uid" -ne 0 ] || die "frontend image runs as root (uid 0)"
log "  frontend uid: $frontend_uid"

log "Minimal container smoke check ..."
docker run --rm --entrypoint gunicorn bugfixer-backend:ci --version
docker run --rm --entrypoint celery bugfixer-backend:ci --version
docker run --rm --entrypoint sh bugfixer-frontend:ci -c "test -f server.js && echo 'server.js present'"
docker run --rm --entrypoint node bugfixer-frontend:ci --version

log "Image CI sequence passed. (Local-only tags 'bugfixer-backend:ci'/'bugfixer-frontend:ci' — remove with: docker rmi bugfixer-backend:ci bugfixer-frontend:ci)"
