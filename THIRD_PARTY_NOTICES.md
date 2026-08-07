# Third-Party Notices

Quorfix Community is licensed under Apache-2.0 (see [LICENSE](./LICENSE)). It depends on the
third-party open-source packages listed below. This file is a summary for convenience; the
authoritative license text for each package is the one distributed with that package (in its own
source repository or, once installed, under `node_modules/<package>/LICENSE` or the installed
Python package's own metadata).

No fonts, icon packs, or other non-code creative assets are bundled — the frontend uses the
browser's default system font stack and no icon library. `frontend/e2e/fixtures/` contains a
synthetic 1×1 pixel PNG generated for test purposes, not a third-party image asset.

`CODE_OF_CONDUCT.md` is adapted from the [Contributor Covenant](https://www.contributor-covenant.org),
version 2.1 — see that file's own "Attribution" section for the specific license
(Creative Commons Attribution 4.0 International) it's used under.

Audited against `backend/requirements.txt`, `backend/requirements-dev.txt`, and
`frontend/package.json` as of Phase 6 Chunk K. Regenerate/re-verify this list whenever a
dependency is added, removed, or upgraded — see `docs/RELEASING.md`'s pre-release checklist.

## Backend (Python)

| Package | License |
| --- | --- |
| Django | BSD-3-Clause |
| djangorestframework | BSD |
| django-cors-headers | MIT |
| drf-spectacular | BSD |
| psycopg[binary] | LGPL-3.0 |
| celery | BSD-3-Clause |
| redis | MIT |
| gunicorn | MIT |
| whitenoise | MIT |
| pytest (development only) | MIT |
| pytest-django (development only) | BSD |
| ruff (development only) | MIT |

`psycopg[binary]`'s LGPL-3.0 license is a dynamic-linking-compatible copyleft license commonly
used for database drivers; Quorfix uses it as an ordinary dependency (imported, not modified or
statically relinked), which does not extend LGPL obligations to the rest of this Apache-2.0
codebase. If your own deployment redistributes modified `psycopg` source, LGPL-3.0's own terms
apply to that separately.

Each package's transitive dependencies carry their own licenses (predominantly MIT/BSD/Apache-2.0
across the Python and Node ecosystems) — not enumerated individually here; run `pip-audit` /
`pip show <package>` (backend) or inspect `frontend/package-lock.json` (frontend) for the full
resolved dependency tree.

## Frontend (JavaScript/TypeScript)

| Package | License |
| --- | --- |
| next | MIT |
| react | MIT |
| react-dom | MIT |
| react-hook-form | MIT |
| @hookform/resolvers | MIT |
| zod | MIT |
| @tanstack/react-query | MIT |
| recharts | MIT |
| typescript (development only) | Apache-2.0 |
| tailwindcss (development only) | MIT |
| @tailwindcss/postcss (development only) | MIT |
| postcss (development only) | MIT |
| eslint (development only) | MIT |
| eslint-config-next (development only) | MIT |
| @playwright/test (development only) | Apache-2.0 |
| vitest (development only) | MIT |
| @vitejs/plugin-react (development only) | MIT |
| @testing-library/react (development only) | MIT |
| @testing-library/jest-dom (development only) | MIT |
| @testing-library/user-event (development only) | MIT |
| jsdom (development only) | MIT |
| @axe-core/playwright (development only) | MPL-2.0 |
| @types/node, @types/react, @types/react-dom (development only) | MIT |

`@axe-core/playwright`'s MPL-2.0 license is file-level copyleft (modifications to MPL-licensed
files themselves must be shared under MPL-2.0 if redistributed) and, like `psycopg[binary]`
above, is used here as an ordinary, unmodified development-only dependency — it does not extend
to the rest of this codebase.

## Infrastructure images (not code dependencies, but distributed as part of the Compose stack)

| Image | License |
| --- | --- |
| `postgres:16-alpine` | PostgreSQL License (permissive) + Alpine Linux packages (various OSS) |
| `redis:7-alpine` | RSALv2/SSPLv1 dual license (Redis 7.x) + Alpine Linux packages |
| `node:22-slim` (frontend build stage) | Various OSS (Node.js: MIT-style; Debian packages: various) |
| `python:3.12-slim` (backend build stage, see `backend/Dockerfile`) | PSF License + Debian packages |

These are pulled, not modified or redistributed by this project beyond ordinary `docker build`
layering — see each image's own Docker Hub / vendor page for complete license terms.
