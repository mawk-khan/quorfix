# Contributing to Quorfix

Thanks for considering a contribution. This document covers how to propose a change, the
conventions this repository follows, and what to expect from review.

**Security vulnerabilities do not go here.** See `docs/SECURITY.md` — do not open a public issue
or pull request describing an unpatched vulnerability.

## Before you start

- Read [CLAUDE.md](./CLAUDE.md) — it's the authoritative architecture and product-boundary
  document (Community vs. Professional, modular-monolith rules, tenant-isolation requirements,
  backend/frontend standards). Code that violates it will be asked to change in review even if
  it otherwise works.
- Check open issues and pull requests first — someone may already be working on the same thing.
- For a substantial change (new feature, architectural change, anything touching the
  Community/Professional boundary), open an issue to discuss the approach before writing code.
  Small, focused fixes (a bug fix, a docs correction, a test-coverage gap) don't need this step.

## Development setup

See `docs/INSTALLATION.md` for the full local development setup
(`git clone` → `docker compose up --build` → migrate → seed or create an account).

## Making a change

1. Fork the repository and create a branch off `master`.
2. Make your change. Keep it focused — a bug fix doesn't need an unrelated refactor bundled in,
   and a one-shot script doesn't need a reusable abstraction built around it (see CLAUDE.md
   "During implementation").
3. Follow the existing patterns in the file/app you're touching before introducing a new one.
4. Add or update tests. This project expects, per CLAUDE.md's testing section, the appropriate
   mix of unit, API integration, permission, tenant-isolation, capability, validation,
   concurrency, frontend component, and Playwright workflow tests for what you changed — not
   every category for every change, but don't skip the ones that actually apply.
5. Update documentation when setup, behavior, or routes change (`docs/ACCESS_AND_TESTING.md` in
   particular is updated after every phase/chunk that does — see CLAUDE.md's working
   procedure).

## Before opening a pull request

Backend:

```bash
cd backend
ruff format .
ruff check .
pytest
```

Frontend:

```bash
cd frontend
npm run lint
npm run typecheck
npm test
```

Or run the same sequences CI runs, locally, via `make ci-backend` / `make ci-frontend` (see
README.md "Continuous integration" for what each covers and their prerequisites).

## Pull request expectations

- Fill in the pull request template (`.github/PULL_REQUEST_TEMPLATE.md`) — what changed, why,
  and how you tested it.
- Keep the diff scoped to what the description says changed. Unrelated formatting/reformatting
  of files you didn't otherwise touch makes review harder, not easier.
- CI (`.github/workflows/backend.yml`, `frontend.yml`, `e2e.yml`) must pass.
- Be ready to discuss and revise — review comments are about the code, not a judgment of the
  contributor.

## Coding conventions

- **Backend**: Python/Django, service-layer business logic, thin views/serializers, selectors
  for complex queries, `select_related`/`prefetch_related` to avoid N+1s, atomic transactions
  for multi-record operations, UUID primary keys, timezone-aware timestamps — see CLAUDE.md
  "Backend standards" for the full list.
- **Frontend**: server components by default, client components only where interactivity
  requires it, a typed API layer (no ad hoc `fetch` calls from presentation components),
  filters synced to URL search parameters, accessible semantic HTML — see CLAUDE.md "Frontend
  standards".
- **Security**: authorization is enforced on the backend, never the frontend alone; validate
  attachment size/content-type/filename/organization/ownership; sanitize rendered user content;
  never log secrets — see CLAUDE.md "Security".
- **Multi-tenancy**: every tenant-owned record belongs to an organization, every authenticated
  query is scoped to it, and cross-organization access must be structurally impossible, not just
  filtered in the UI — covered by dedicated tenant-isolation tests for a reason.

## Community vs. Professional

Community must never import Professional modules, and must remain fully functional with every
Professional module absent or disabled. If your change touches an extension point
(`capability_registry`, `workflow_registry`, etc.), see CLAUDE.md "Capabilities" and
"Edition boundaries" before assuming where a feature belongs.

## Code of conduct

Participation in this project is governed by [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).

## License

By contributing, you agree your contribution is licensed under this repository's Apache-2.0
license (see [LICENSE](./LICENSE)) for Community code. Professional-licensed code is out of
scope for external contribution while Professional does not yet exist in this repository.
