# syntax notes: plain Dockerfile syntax only (no BuildKit-only features),
# so `DOCKER_BUILDKIT=0 docker compose build` keeps working on hosts without
# a buildx plugin, same as before this refactor.

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# ---- deps: production-only Python dependencies, shared by every later stage ----
FROM base AS deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---- dev: adds dev/test dependencies + full source. Used by docker-compose.yml
# (backend/celery_worker services set target: dev) for local development —
# never used for anything production-oriented. ----
FROM deps AS dev
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---- collectstatic: build-time only. Produces the hashed/compressed static/
# tree (see config/settings/production.py's STORAGES) that the production
# stage below copies from — collectstatic never runs at container startup,
# so the runtime user never needs write access to STATIC_ROOT. The dummy
# SECRET_KEY only satisfies Django's own "SECRET_KEY must not be empty"
# guard so settings can be imported; --skip-checks skips the real
# apps.core.checks production checks, which legitimately require real
# secrets/hosts/etc. that don't exist at build time. Neither value is a real
# secret, and RUN-scoped shell variables are not persisted as image layer
# metadata the way ARG/ENV would be. ----
FROM deps AS collectstatic
COPY . .
RUN DJANGO_SETTINGS_MODULE=config.settings.production \
    DJANGO_SECRET_KEY=build-time-collectstatic-only \
    python manage.py collectstatic --noinput --skip-checks

# ---- production: minimal runtime image — no dev/test dependencies, no
# source bind mount, non-root. This is the default (final) stage, matching
# frontend/Dockerfile's convention, so `docker build ./backend` with no
# --target produces the production image. ----
FROM deps AS production

# Build metadata only — never claims byte-for-byte reproducibility (build
# timestamps, package index state, etc. can still vary). VERSION/VCS_REF are
# ordinary build args, not secrets, so there is no history-persistence
# concern in passing them this way (unlike credentials, which must never go
# through ARG).
ARG VERSION=dev
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="Quorfix backend" \
      org.opencontainers.image.description="Quorfix Community backend (Django/DRF API + Celery worker image)" \
      org.opencontainers.image.source="https://github.com/mawk-khan/quorfix" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.version="${VERSION}"

# A dedicated, non-/app data directory for local attachments — kept
# separate from the application source tree so the two can have different
# ownership/writability without one leaking into the other. Created (empty)
# and chowned here so that when docker-compose.prod.yml mounts a named
# volume at this exact path, Docker's own "populate an empty new volume
# from the image directory it's mounted over" behavior gives the volume the
# same ownership from its very first use — no root-only chown step needed
# at container startup.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/attachments \
    && chown app:app /data/attachments

COPY --chown=app:app . .
COPY --from=collectstatic --chown=app:app /app/staticfiles ./staticfiles
RUN chmod +x entrypoint.sh

USER app

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--config", "gunicorn.conf.py"]
