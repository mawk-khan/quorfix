# Quorfix

Quorfix is an open-core bug-tracking platform: open-core bug tracking for software teams.

**Status: pre-1.0 beta.** No tagged release has shipped yet — see
[Known beta limitations](#known-beta-limitations) and `docs/SECURITY.md` before running this
anywhere beyond your own local/disposable environment.

- **Official domain:** quorfix.com *(not yet confirmed live — do not assume DNS, TLS, email, or
  hosting are configured merely because the name is used in this documentation)*
- **Official repository:** [github.com/mawk-khan/quorfix](https://github.com/mawk-khan/quorfix)

- **Community** — free, open source (Apache-2.0), for small teams. Covers authentication,
  a single organization, projects, bug creation/management, the standard workflow,
  assignment, comments, attachments, tags, watchers, activity history, a basic dashboard,
  search/filters, basic notifications, and the core REST API.
- **Professional** — extends Community with multiple organizations, custom roles,
  custom workflows, custom fields, saved views, advanced analytics, scheduled reports,
  SLA tracking, automation rules, API tokens, webhooks, third-party integrations, SSO/SAML,
  SCIM, audit exports, AI assistance, and white labeling. Professional modules are licensed
  separately and are optional at runtime — Community works fully without them. **No
  Professional code exists in this repository yet** — see `CLAUDE.md` for the architectural
  boundary that keeps it that way.

See [CLAUDE.md](./CLAUDE.md) for the full architecture and contribution rules, and
[CHANGELOG.md](./CHANGELOG.md) for what's actually shipped, version by version.

## Stack

- **Frontend**: Next.js (App Router), TypeScript (strict), Tailwind CSS, React Hook Form,
  Zod, TanStack Query, Recharts, Playwright.
- **Backend**: Python, Django, Django REST Framework, PostgreSQL, Redis, Celery, Pytest,
  Ruff.
- **Infrastructure**: Docker, Docker Compose, S3-compatible object storage (planned — see
  [Known beta limitations](#known-beta-limitations)), GitHub Actions.

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

## Quick start (local development)

```bash
git clone https://github.com/mawk-khan/quorfix.git
cd quorfix
cp .env.example .env
docker compose up --build
```

This starts Postgres, Redis, the Django backend (`localhost:8000`), a Celery worker,
and the Next.js frontend (`localhost:3000`). The frontend proxies `/api/*` to the
backend, so the browser only ever talks to one origin in development.

Then, in a second terminal:

```bash
docker compose exec backend python manage.py migrate

# Either create a single admin account:
docker compose exec backend python manage.py createsuperuser

# ...or seed a full set of development-only demo data (one organization, one
# user per Community role, three example projects). Idempotent, and refuses
# to run under production settings:
docker compose exec backend python manage.py seed_demo   # or: make seed-demo
```

API documentation (OpenAPI/Swagger) is served at `/api/docs/` once the backend is running.

See [docs/INSTALLATION.md](./docs/INSTALLATION.md) for the full installation guide (development
and production), including a clean-install smoke test.

## Production

`docker-compose.prod.yml` is a cloud-neutral, production-oriented **example** configuration —
immutable, non-root application images; a named volume for local attachments shared by the
backend and Celery worker; readiness/liveness checks; no source bind mounts; **no high-availability
or zero-downtime deployment guarantee** (single instance per service). It does not replace
`docker-compose.yml`, which remains the local-development configuration.

```bash
make prod-config   # validate the resolved configuration
make prod-build    # build the production images
make prod-up       # start db, redis, backend, celery_worker, frontend
make prod-migrate  # explicit, separate step — never run automatically
```

See [docs/INSTALLATION.md](./docs/INSTALLATION.md) for required production origins
(`quorfix.com` examples), reverse-proxy/TLS expectations, and a clean-install walkthrough;
[docs/BACKUP_AND_RESTORE.md](./docs/BACKUP_AND_RESTORE.md) for PostgreSQL and local
attachment backup/restore procedures; and [docs/UPGRADING.md](./docs/UPGRADING.md) for the
upgrade, migration, and rollback procedure.

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
| `backend.yml` | push/PR touching `backend/**` | Ruff, Django system check, migration drift/unapplied checks, full pytest suite, OpenAPI generation+validation, Community-only isolation, pip-audit on both `requirements.txt` and `requirements-dev.txt` (both blocking) |
| `frontend.yml` | push/PR touching `frontend/**` | ESLint, TypeScript, Vitest, production build, npm audit (blocking) |
| `e2e.yml` | push/PR touching `backend/**`, `frontend/**`, `docker-compose.yml` | Full Playwright suite against a disposable `docker compose` stack (Postgres, Redis, backend, Celery worker, frontend) |
| `images.yml` | push to `master` / PR touching Docker build files / manual dispatch | Builds both production images, verifies non-root runtime users, minimal container smoke check — never pushes |

`release.yml` triggers only on a `vX.Y.Z[-prerelease]` tag push, validates the tag matches
`VERSION`, requires `backend.yml`/`frontend.yml` to pass first, then builds and pushes images to
GHCR — see [docs/RELEASING.md](./docs/RELEASING.md). No tag has been pushed yet.

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
model, dependency scan policy). **The security contact in that document is a placeholder — this
is a known, tracked release blocker (see `docs/SECURITY.md` and `CHANGELOG.md`), not something
resolved yet.**

## Contributing and support

- [CONTRIBUTING.md](./CONTRIBUTING.md) — how to propose a change, coding conventions, PR
  expectations.
- [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) — community conduct expectations and how to report
  a violation.
- Bug reports and feature requests: [GitHub Issues](https://github.com/mawk-khan/quorfix/issues)
  using the provided templates (`.github/ISSUE_TEMPLATE/`) — **never a security report**, see
  above.
- **Support model:** this is a community-supported, unfunded beta project. There is no
  commercial support offering for Community; Professional's commercial-support tooling (see
  `CLAUDE.md`) does not exist yet.

## Known beta limitations

Summarized here; see [CHANGELOG.md](./CHANGELOG.md) for the full, versioned list.

- One active organization per Community installation (a product boundary, not a bug).
- Local filesystem attachment storage only — no S3-compatible provider yet.
- Analytics date ranges use the server's configured timezone (UTC), not a per-organization one.
- List pagination uses `OFFSET`, with real cost on very deep pages — see `docs/PERFORMANCE.md`.
- Limited concurrent-load testing; no zero-downtime deployment guarantee.
- TLS termination and a reverse proxy are the operator's responsibility.
- No Professional features exist in this repository.
- No formal WCAG conformance certification.
- **No monitored security contact yet — see [Security](#security).**

## Licensing

Community code (everything outside `professional/` directories) is licensed under
Apache-2.0 — see [LICENSE](./LICENSE). Professional modules, once added, ship under a
separate commercial license and are not covered by the Apache-2.0 grant. Third-party
dependency licenses are tracked in [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
