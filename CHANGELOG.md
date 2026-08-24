# Changelog

All notable changes to Quorfix are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
uses [Semantic Versioning](https://semver.org/). See `docs/RELEASING.md` for how a release is cut
and `VERSION` (repository root) for the current source-of-truth version string.

## [Unreleased]

Nothing yet.

## [1.0.0] — 2026-08-24

First stable Community release. An earlier `0.5.0-beta.1` entry existed in this file during
development but was **never tagged or published** — the project owner made the decision to
proceed directly to `1.0.0` instead of cutting that beta, so this entry supersedes it and is the
first real release this changelog describes. Nothing below claims `0.5.0-beta.1` shipped, because
it did not.

### Added

- **Accounts and organization setup** — first-run instance setup, email/password
  authentication, session-based auth, one active organization per Community installation,
  standard roles (administrator, developer, QA, reporter, viewer), team invitations
  (invite/accept/revoke), member role management.
- **Projects** — create/edit/archive/restore, project keys, project leads, per-project bug
  key-numbering.
- **Bug lifecycle** — creation, standard workflow (new → triaged → assigned → in progress →
  ready for QA → resolved → closed, plus reopened/blocked/deferred/duplicate/cannot-reproduce/
  won't-fix branches), assignment, status/priority/severity, tags, watchers, due dates,
  optimistic-concurrency version conflicts, sequential human-readable keys (e.g. `BFW-123`) safe
  under concurrent creation.
- **Comments and mentions** — threaded comments on bugs, `@mention` parsing and resolution,
  edit window for authors, administrator moderation (edit/delete any comment), comment-based
  notification triggers.
- **Local attachments** — upload/download for bug attachments, content-type and size validation,
  signature verification against the declared content type, sanitized filenames, local
  filesystem storage provider behind a swappable `StorageProvider` interface (no S3 provider
  yet — see [Known limitations](#known-limitations)).
- **Notifications** — in-app notifications for assignment/mention/comment/status-change/reopen
  events, per-user-per-event email preferences, deduplicated delivery, basic email notifications.
- **Dashboard analytics** — open/overdue/new/resolved bug summaries, status and severity
  distributions, resolution-time-by-priority, created-vs-resolved trends, developer workload,
  recent activity feed, date-range and per-project filtering synced to the URL.
- **Production containers** — multi-stage, non-root Docker images for backend and frontend,
  `docker-compose.prod.yml` (cloud-neutral example topology), Gunicorn + Celery worker
  processes, health (`/api/health/`) and readiness (`/api/health/ready/`) endpoints, OCI image
  labels (title/description/source/version/revision).
- **Backup and restore** — coordinated PostgreSQL + local-attachment recovery sets, checksum
  verification, versioned manifest format, `quorfix-backup-` naming (see
  `docs/BACKUP_AND_RESTORE.md`).
- **Upgrade tooling** — migration-drift/unapplied-migration checks, non-destructive post-upgrade
  smoke check, documented rollback procedure.
- **Security hardening** — dependency scanning (`pip-audit`/`npm audit`) in CI, production
  fail-fast configuration checks (`quorfix.E0xx`), attachment content-type/signature validation,
  path-traversal prevention, rate limiting on sensitive endpoints, secure cookie/HTTPS defaults,
  tenant-isolation test coverage across every Community app.
- **Accessibility** — automated `axe-core` scanning in the Playwright suite, keyboard-navigation
  coverage, focus management on client-side navigation and destructive-dialog flows, skip link,
  accessible names/labels across forms and interactive components (see [Known
  limitations](#known-limitations) for what this does not claim).
- **Performance validation** — disposable large-scale (~100,000-bug) dataset generation and
  measurement tooling, evidence-based indexing/query decisions documented in
  `docs/PERFORMANCE.md`.
- **Observability** — structured JSON logging in production, request-correlation IDs threaded
  through HTTP requests and the Celery tasks they dispatch, safe authentication/operational
  event logging, documented sensitive-data policy (see `docs/OBSERVABILITY.md`).
- **Quorfix branding** — product rename from this project's pre-launch working title to Quorfix
  across user-facing text, documentation, identifiers, and release tooling (see
  `docs/ACCESS_AND_TESTING.md` Phase 6 Chunk K for the full scope and reasoning).
- **Confirmed contact channels** — `security@quorfix.com` (vulnerability reports, see
  `docs/SECURITY.md`) and `conduct@quorfix.com` (Code of Conduct enforcement, see
  `CODE_OF_CONDUCT.md`) are real, monitored addresses.
- **Secure public demo access** — a Quick Access flow letting a visitor sign in directly as one
  of five fixed personas (administrator, developer, QA, reporter, viewer) without a real account,
  backed by strict server-side role/membership validation and protection against mutating the
  demo personas' own identity or security fields.
- **Public-demo hardening** — environment-gated demo mode, a dedicated demo mail sink so demo
  visitors' email never leaves the instance, demo-scoped mutation rate limiting, and defense in
  depth for the public demo deployment (see `docs/SECURITY.md`, `docs/DEMO_DEPLOYMENT.md`).
- **Demo lifecycle and deployment tooling** — `scripts/demo` (deploy/start/stop/restart/logs/
  backup/health/reset-demo), environment validation, and an environment-gated, explicitly
  confirmed, advisory-locked, transactional demo reset that restores the canonical demo dataset
  while leaving non-demo data, staff, and superuser accounts untouched (see
  `docs/DEMO_DEPLOYMENT.md`).
- **Community feature freeze** — `docs/COMMUNITY_RELEASE_POLICY.md` establishes the frozen
  Community `v1.0.0` product boundary and what Community continues to accept (security/bug/
  compatibility fixes, dependency maintenance, documentation, scoped usability improvements)
  after this release. Community remains a maintained product — the freeze means stable scope,
  not end-of-life.
- **Community/Professional edition boundary** — `docs/EDITION_BOUNDARIES.md` and
  `docs/LICENSING.md` formally define the repository, dependency-direction, extension, and
  licensing boundary between Quorfix Community (Apache-2.0, this repository) and the separate,
  commercially-licensed Quorfix Professional (private repository, not yet created, no code in
  this repository).

### Known limitations

- Community supports **one active organization per installation** — this is a Community product
  boundary (see `CLAUDE.md`), not a bug; Professional will support multiple organizations.
- Attachments use **local filesystem storage only** — no S3-compatible object storage provider
  exists yet (the `StorageProvider` interface is ready for one).
- Analytics date-range boundaries use the server's **configured timezone (UTC)**, not a
  per-organization timezone — Organization has no timezone field yet.
- List pagination uses **`OFFSET`**, which has real cost on very deep pages against large
  datasets — see `docs/PERFORMANCE.md` for the measured behavior and mitigation guidance.
- Only **limited concurrent-load testing** has been performed — see `docs/PERFORMANCE.md`'s own
  scope note.
- `docker-compose.prod.yml` is a **single-instance-per-service** example topology with **no
  zero-downtime deployment guarantee** — an upgrade briefly stops and restarts services (see
  `docs/UPGRADING.md`).
- **TLS termination and a reverse proxy are the operator's responsibility** — no container here
  terminates TLS or sends HSTS (see `docs/SECURITY.md` "HTTPS / reverse-proxy responsibility").
- **No Professional features** exist in this release — licensing, entitlements, custom
  workflows/fields, SSO/SAML/SCIM, advanced analytics, integrations, and automation are all
  out of scope for Community and are not included here (see `docs/EDITION_BOUNDARIES.md` for the
  recommended Professional boundary, and `docs/COMMUNITY_RELEASE_POLICY.md` for what Community
  does and doesn't accept going forward).
- **No formal WCAG conformance certification** — automated `axe-core` coverage plus a manual
  pass exist, but no live screen-reader (NVDA/JAWS/VoiceOver/Orca) session has been performed;
  see `docs/ACCESS_AND_TESTING.md`'s accessibility chunk entry for exactly what was and wasn't
  verified.
