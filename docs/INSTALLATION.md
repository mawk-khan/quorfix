# Installation Guide

Covers both a local development install and the production-oriented example Compose stack.
For day-to-day local URLs, demo credentials, and a manual test checklist once you're running,
see `docs/ACCESS_AND_TESTING.md`. For upgrading an existing install, see `docs/UPGRADING.md`.
For backup/restore, see `docs/BACKUP_AND_RESTORE.md`.

## 1. Development installation

Prerequisites: Docker and Docker Compose.

```bash
git clone https://github.com/mawk-khan/quorfix.git
cd quorfix
cp .env.example .env
docker compose up --build
```

This starts `db` (PostgreSQL), `redis`, `backend` (Django, `localhost:8000`), `celery_worker`,
and `frontend` (Next.js, `localhost:3000`). The frontend proxies `/api/*` to the backend, so the
browser only ever talks to one origin.

In a second terminal:

```bash
# Explicit — never run automatically.
docker compose exec backend python manage.py migrate

# Either create a single admin account:
docker compose exec backend python manage.py createsuperuser

# ...or seed development-only demo data (one organization, one user per
# Community role, three example projects). Idempotent; refuses to run under
# production settings.
docker compose exec backend python manage.py seed_demo   # or: make seed-demo
```

Visit `http://localhost:3000`. API documentation (OpenAPI/Swagger) is at
`http://localhost:8000/api/docs/`.

### Persistent local volumes

`docker-compose.yml` defines one named volume, `postgres_data` (PostgreSQL's data directory).
Local attachments live on a bind mount (`./backend:/app`) under the checkout itself in
development, not a named volume — see `docker-compose.prod.yml`'s `attachments_data` for the
production equivalent.

## 2. Production-oriented Compose

`docker-compose.prod.yml` is a cloud-neutral **example** configuration: immutable, non-root
application images; a named volume (`attachments_data`) for local attachments shared by the
`backend` and `celery_worker` services; readiness/liveness checks; no source bind mounts.

**This is not a high-availability deployment.** Each service runs as a single instance; there is
no built-in load balancing, failover, or zero-downtime deployment mechanism — an upgrade briefly
stops and restarts services (see `docs/UPGRADING.md`). Adapt the topology yourself if your
environment needs more than this.

### 2.1 Required origins

The example architecture is same-origin: the browser only ever talks to the frontend's public
origin, which proxies `/api/*` to the backend internally
(`BACKEND_INTERNAL_URL=http://backend:8000`, container-to-container only — this never becomes
`api.quorfix.com` or a publicly reachable address of its own).

```bash
# .env, production example (only include www.quorfix.com if that subdomain
# is actually intended to serve traffic):
DJANGO_ALLOWED_HOSTS=quorfix.com,www.quorfix.com,backend
CSRF_TRUSTED_ORIGINS=https://quorfix.com,https://www.quorfix.com
FRONTEND_BASE_URL=https://quorfix.com
```

`backend` must stay in `DJANGO_ALLOWED_HOSTS` regardless of your public hostname — the
frontend's internal proxy forwards requests with `Host: backend:8000`, and Django would
otherwise reject every proxied `/api/*` request with 400 Bad Request. See `.env.example` for
every other required/optional variable, each documented inline.

Redirect and canonical-host handling (e.g. `www` → apex, or the reverse, and all TLS
termination) is a **reverse-proxy responsibility**, not something this application implements —
see [2.4 Reverse proxy and TLS](#24-reverse-proxy-and-tls) below.

Purchasing `quorfix.com` does not, by itself, configure DNS, TLS, email delivery, or hosting —
none of that is assumed to already exist merely because these examples use that domain.

### 2.2 Bring the stack up

```bash
cp .env.example .env
# edit .env: DJANGO_SECRET_KEY, POSTGRES_PASSWORD, DJANGO_ALLOWED_HOSTS,
# CSRF_TRUSTED_ORIGINS, FRONTEND_BASE_URL, EMAIL_* — see .env.example

make prod-config    # validate the resolved configuration first
make prod-build      # build the production images
make prod-up         # start db, redis, backend, celery_worker, frontend

# Explicit, separate step — never run automatically by prod-up:
make prod-migrate
```

`make prod-check` runs Django's production system checks (`quorfix.E0xx` — see
`backend/apps/core/checks.py`) against your resolved configuration without starting the
long-running services; the backend's own container entrypoint also runs this on every start, so
a misconfigured deployment fails loudly at startup rather than serving broken requests.

### 2.3 Persistent volumes

| Volume | Contents | Mounted in |
| --- | --- | --- |
| `postgres_data` | PostgreSQL data directory | `db` |
| `redis_data` | Redis RDB snapshots (operational state — Celery broker/result backend, throttle counters, analytics cache; not a backup target on its own) | `redis` |
| `attachments_data` | Uploaded attachment files | `backend`, `celery_worker` (both, at the same path — a hard requirement, not a convenience) |

`make prod-down` stops and removes containers but leaves these volumes intact. See
`docs/BACKUP_AND_RESTORE.md` for how to actually back up `postgres_data` and `attachments_data`
(treated as one coordinated recovery set).

### 2.4 Reverse proxy and TLS

No container in this stack terminates TLS or sends `Strict-Transport-Security` — only
`frontend`'s plain-HTTP port is published, and an operator-provided reverse proxy in front of it
is expected to terminate TLS, forward `X-Forwarded-Proto`, and handle canonical-host
redirects. See `docs/SECURITY.md` "HTTPS / reverse-proxy responsibility" for the full reasoning,
including why sending HSTS from this application itself would be a false promise.

### 2.5 Health and readiness

- `GET /api/health/` — liveness: process is up, nothing more. Never touches the database, cache,
  or attachment storage.
- `GET /api/health/ready/` — readiness: checks database, cache, and attachment storage; returns
  `503` if any is unhealthy. Point an orchestrator's readiness probe (or your reverse proxy's
  upstream health check) here, not at liveness.

See `docs/OBSERVABILITY.md` "Health and readiness" for what each endpoint logs and doesn't.

## 3. Clean-install smoke test

A minimal, non-destructive sequence to confirm a fresh production-oriented install actually
works end to end:

```bash
make prod-config                                   # 1. config resolves
make prod-build                                     # 2. images build
make prod-up                                        # 3. stack starts
make prod-migrate                                   # 4. schema applied

curl -f http://localhost:8000/api/health/           # 5. liveness
curl -f http://localhost:8000/api/health/ready/     # 6. readiness (db/cache/attachments)
curl -f http://localhost:3000/                      # 7. frontend responds

docker compose -f docker-compose.prod.yml exec backend \
  python manage.py showmigrations --plan             # 8. every migration applied ([X])

make upgrade-smoke                                  # 9. the same non-destructive checks,
                                                     #    scripted (see docs/UPGRADING.md)
```

If you seed demo data for a walkthrough afterward, remember `seed_demo` refuses to run under
production settings by design — it's a development-only command; see
`docs/ACCESS_AND_TESTING.md` for the equivalent production-safe first-run flow
(`manage.py createsuperuser` or the `/setup` page).
