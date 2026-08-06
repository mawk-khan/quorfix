# Bug Fixer

Bug Fixer is an open-core bug-tracking platform.

- **Community** — free, open source (Apache-2.0), for small teams. Covers authentication,
  a single organization, projects, bug creation/management, the standard workflow,
  assignment, comments, attachments, tags, watchers, activity history, a basic dashboard,
  search/filters, basic notifications, and the core REST API.
- **Professional** — extends Community with multiple organizations, custom roles,
  custom workflows, custom fields, saved views, advanced analytics, scheduled reports,
  SLA tracking, automation rules, API tokens, webhooks, third-party integrations, SSO/SAML,
  SCIM, audit exports, AI assistance, and white labeling. Professional modules are licensed
  separately and are optional at runtime — Community works fully without them.

See [CLAUDE.md](./CLAUDE.md) for the full architecture and contribution rules.

## Stack

- **Frontend**: Next.js (App Router), TypeScript (strict), Tailwind CSS, React Hook Form,
  Zod, TanStack Query, Recharts, Playwright.
- **Backend**: Python, Django, Django REST Framework, PostgreSQL, Redis, Celery, Pytest,
  Ruff.
- **Infrastructure**: Docker, Docker Compose, S3-compatible object storage, GitHub Actions.

## Project layout

```
backend/            Django project (modular monolith)
  config/           Settings, URLs, Celery app, WSGI/ASGI entrypoints
  apps/             Community domain apps (accounts, organizations, projects, bugs, ...)
  apps/core/         Shared infrastructure: base models, pagination, extension registries
  professional/     Optional Professional Django apps (empty in Community-only installs)
frontend/           Next.js App Router project
  src/app/          Routes
  src/lib/api/      Typed API client layer
  professional/     Optional Professional UI modules
  e2e/              Playwright tests
```

## Local development

1. Copy the environment template and fill in real values:

   ```bash
   cp .env.example .env
   ```

2. Start the stack:

   ```bash
   docker compose up --build
   ```

   This starts Postgres, Redis, the Django backend (`localhost:8000`), a Celery worker,
   and the Next.js frontend (`localhost:3000`). The frontend proxies `/api/*` to the
   backend, so the browser only ever talks to one origin in development.

3. Run migrations (first run, and after any model change):

   ```bash
   docker compose exec backend python manage.py migrate
   ```

4. Create an admin user:

   ```bash
   docker compose exec backend python manage.py createsuperuser
   ```

5. Or, instead of step 4, seed a full set of **development-only** demo data — one
   organization, one user per Community role, and three example projects:

   ```bash
   docker compose exec backend python manage.py seed_demo
   # or:
   make seed-demo
   ```

   Idempotent (safe to re-run) and refuses to run under production settings. It prints
   the demo login credentials to the console — development-only accounts, never seeded
   or exposed in production.

API documentation (OpenAPI/Swagger) is served at `/api/docs/` once the backend is running.

## Production

`docker-compose.prod.yml` is a cloud-neutral, production-oriented example configuration —
immutable, non-root application images; a named volume for local attachments shared by the
backend and Celery worker; readiness/liveness checks; no source bind mounts. It does not
replace `docker-compose.yml`, which remains the local-development configuration.

```bash
make prod-config   # validate the resolved configuration
make prod-build    # build the production images
make prod-up       # start db, redis, backend, celery_worker, frontend
make prod-migrate  # explicit, separate step — never run automatically
```

See [docs/BACKUP_AND_RESTORE.md](./docs/BACKUP_AND_RESTORE.md) for PostgreSQL and local
attachment backup/restore procedures, and [docs/UPGRADING.md](./docs/UPGRADING.md) for the
upgrade, migration, and rollback procedure. A full production deployment guide is a later,
dedicated documentation phase — this is the current state of the container setup, not a
complete operations manual.

## Observability

Structured logs (JSON in production), a request correlation ID (`X-Request-ID`) threaded through
every HTTP request and the Celery tasks it dispatches, and a documented sensitive-data policy —
see [docs/OBSERVABILITY.md](./docs/OBSERVABILITY.md) for log format, correlation behavior across
Django/Gunicorn/Celery, and troubleshooting examples. No external monitoring vendor is required.

## Testing

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
pytest
```

Frontend:

```bash
cd frontend
npm install
npm run lint
npm run typecheck
npm run test:e2e   # requires the dev server running
```

## Continuous integration

Four GitHub Actions workflows (`.github/workflows/`) enforce the release-readiness baseline:

| Workflow | Runs on | What it checks |
| --- | --- | --- |
| `backend.yml` | push/PR touching `backend/**` | Ruff, Django system check, migration drift/unapplied checks, full pytest suite, OpenAPI generation+validation, Community-only isolation, pip-audit (non-blocking) |
| `frontend.yml` | push/PR touching `frontend/**` | ESLint, TypeScript, Vitest, production build, npm audit (blocking) |
| `e2e.yml` | push/PR touching `backend/**`, `frontend/**`, `docker-compose.yml` | Full Playwright suite against a disposable `docker compose` stack (Postgres, Redis, backend, Celery worker, frontend) |
| `images.yml` | push to `master` / PR touching Docker build files / manual dispatch | Builds both production images, verifies non-root runtime users, minimal container smoke check — never pushes |

`release.yml` is a dormant skeleton that only triggers on a `vX.Y.Z` tag push — no chunk of work so far has created one.

No repository URL is embedded here for status badges — this checkout's `origin` remote isn't a public GitHub URL, so a badge here would either be wrong or invented; add real badges once the project has a public GitHub repository to point them at.

Local commands mirroring each workflow (see each workflow's own file for the authoritative, exact sequence):

```bash
make ci-backend         # requires: docker compose up -d db redis backend celery_worker; includes pip-audit
make ci-frontend        # requires: docker compose up -d frontend
make ci-e2e             # destructive to the dev stack's current DB — see scripts/ci_e2e.sh
make ci-images          # builds only, never pushes
make openapi-check
make community-check
```

## Local access and manual testing

For local URLs, demo login credentials, the role permission matrix, a manual test checklist, and
troubleshooting steps, see [docs/ACCESS_AND_TESTING.md](./docs/ACCESS_AND_TESTING.md). That
document is the permanent, maintained reference — it is updated after every completed phase.

## Security

See [docs/SECURITY.md](./docs/SECURITY.md) for the vulnerability reporting process, security
scope, and deployment assumptions (HTTPS/reverse-proxy responsibility, attachment security
model, dependency scan policy). **The security contact in that document is a placeholder — the
project owner must configure a real, monitored contact before any public release.**

## Licensing

Community code (everything outside `professional/` directories) is licensed under
Apache-2.0 — see [LICENSE](./LICENSE). Professional modules, once added, ship under a
separate commercial license and are not covered by the Apache-2.0 grant.
