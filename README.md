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

## Licensing

Community code (everything outside `professional/` directories) is licensed under
Apache-2.0 — see [LICENSE](./LICENSE). Professional modules, once added, ship under a
separate commercial license and are not covered by the Apache-2.0 grant.
