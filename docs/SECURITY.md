# Security Policy

Quorfix Community is pre-1.0, beta software. This document describes what is and isn't
covered, how to report a vulnerability, and the security assumptions this project's
deployment model relies on. It is not a promise of response time, and it is not a complete
security audit — see [Known beta limitations](#known-beta-limitations) for what this document
does not claim.

## Supported versions

Quorfix Community has not yet cut a tagged release (see `docs/UPGRADING.md`). Until a first
release exists, **only the `master` branch is supported** — security fixes land there, not on
any older commit. Once tagged releases exist, this section will be updated to name which
release lines receive security fixes, following the upgrade support policy already documented
in `docs/UPGRADING.md` (one minor version at a time; patch releases within a minor are
supported).

## Beta status

This is beta software. It has not been through an independent third-party security audit or
penetration test. Treat it accordingly: run it behind your own access controls, don't expose
an unaudited beta instance to the public internet holding data you can't afford to lose or
leak, and read [Known beta limitations](#known-beta-limitations) before deciding it's
appropriate for your use case.

## Reporting a vulnerability

Report suspected vulnerabilities privately to:

```
security@quorfix.com
```

- **Do not report a suspected vulnerability through a public GitHub issue.** This repository's
  issue templates (`.github/ISSUE_TEMPLATE/`) deliberately do not offer a "security" category for
  exactly this reason — vulnerability reports must go to the address above, not the public
  tracker.
- Email the address directly rather than following a pre-filled link — this document
  deliberately does not provide a `mailto:` link with a prefilled subject or body, so that no
  sensitive report content is ever drafted into a client before you've reviewed what it contains.
- Say explicitly in the first line of your report that it's a security issue.
- Hold technical/exploit details until you've reached a maintainer directly; see [What not to
  post publicly](#what-not-to-post-publicly).

**We do not promise a response-time SLA.** This is an unfunded beta project; reports will be
looked at, not guaranteed a same-day or same-week reply.

### What to include in a report

- The affected version (Git SHA — see `scripts/inspect_version.sh` /
  `docs/UPGRADING.md` "Version metadata") or, once releases exist, the release tag.
- Steps to reproduce, as concrete as possible (request payloads, an account role, a specific
  endpoint).
- What you expected to happen vs. what actually happened.
- Impact, as you understand it (e.g. "organization A can read organization B's bug titles"),
  not just a proof-of-concept payload.
- Whether you've already made the issue public anywhere.

### What not to post publicly

- Working exploit code or a full attack chain, before a fix is available.
- Real credentials, session cookies, or CSRF tokens obtained during testing — describe how
  you got them, don't paste them.
- Another user's or organization's actual data, if your testing happened to expose someone
  else's real data (this should only happen against your own disposable test instance in the
  first place — see [Security scope](#security-scope)).

## Security scope

**In scope**: this repository's Community code — the Django backend (`backend/apps/`,
excluding the empty `professional/` placeholder), the Next.js frontend (`frontend/src/`,
excluding the empty `professional/` placeholder), the production Dockerfiles and Compose
configuration, and the operator scripts under `scripts/`.

**Out of scope**:
- Professional modules — none exist yet (`backend/professional/` and `frontend/professional/`
  contain only a `README.md` each; see `docs/ACCESS_AND_TESTING.md`'s Community-only
  verification).
- Vulnerabilities in third-party dependencies themselves — report those upstream; see
  [Dependency scan policy](#dependency-scan-policy) for how this project tracks and remediates
  them once disclosed.
- Vulnerabilities that require an already-compromised administrator account, an
  already-compromised database, or physical/root access to the host — Quorfix Community
  trusts its own administrators and its own infrastructure, the same as almost all
  self-hosted software.
- Denial of service via raw traffic volume (that's infrastructure/hosting's responsibility,
  not application code) — application-level resource-exhaustion vectors (e.g. an
  authenticated user filling the attachment volume) are in scope; see
  [Rate limiting](#rate-limiting).

## Deployment assumptions

Running a separate, public invite-only demo/community-beta instance specifically? See
[docs/DEMO_DEPLOYMENT.md](./DEMO_DEPLOYMENT.md) for the required isolation boundary from any
real deployment, the account model, account recovery, and the data reset procedure — this
section and the rest of this document are the general deployment assumptions that apply either
way.

`docker-compose.prod.yml` (see `docs/BACKUP_AND_RESTORE.md`, `docs/UPGRADING.md`) is a
cloud-neutral example, not a complete, hardened production deployment on its own. It assumes:

- An operator-provided reverse proxy sits in front of the `frontend` service and does the
  things this repository's containers deliberately don't: TLS termination, HSTS (see below),
  and any additional network-layer protections the operator's environment needs.
- The Docker host itself is reasonably secured — SSH access, OS patching, and host firewalling
  are the operator's responsibility, not something Quorfix Community's own containers can
  enforce from inside themselves.
- `.env` (and the secrets in it — `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, SMTP credentials)
  is kept outside version control and readable only by whoever operates the deployment. Nothing
  in this repository ever commits, logs, or transmits its contents (see
  `backend/apps/core/checks.py`'s explicit "never includes the value" design, and the security
  logging audit referenced below).

### HTTPS / reverse-proxy responsibility

Quorfix Community's own containers **do not terminate TLS and do not send
`Strict-Transport-Security`**. `frontend/next.config.ts` sends a set of security response
headers (see below) but deliberately excludes HSTS — see that file's own comment for exactly
why: this server is never the TLS-terminating edge in the deployment shape
`docker-compose.prod.yml` describes (only `frontend`'s plain-HTTP port is published; an
operator's reverse proxy is expected to terminate TLS in front of it). Sending HSTS from a
process that cannot itself guarantee HTTPS is always available would be a false promise. If
your reverse proxy terminates TLS (it should), configure HSTS there.

Backend cookies are still hardened regardless: `config/settings/production.py` hardcodes
`SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` to `True` and `SECURE_SSL_REDIRECT` defaults to
`True` (overridable via `DJANGO_SECURE_SSL_REDIRECT` for the internal-only traffic shape
`docker-compose.prod.yml` uses — see that file's own comments) — verified automatically at
startup by `apps.core.checks` and by a dedicated test
(`backend/apps/core/tests/test_production_settings_real_values.py`) that checks the *real*,
committed production settings module, not just a synthetic stand-in.

### Request body / upload size limits

Two independent layers, neither of which is a substitute for the other:

- **Non-file request bodies** (JSON API calls — bug/comment/project creation, etc.): Django's
  own `DATA_UPLOAD_MAX_MEMORY_SIZE` (default 2.5&nbsp;MB, never overridden in this project)
  rejects an oversized body with `RequestDataTooBig` before the view ever runs. This already
  bounds "huge text payload" abuse without any Quorfix-specific code.
- **Attachment uploads** (`multipart/form-data`, `PUT /api/attachments/{id}/bytes/`): Django
  explicitly excludes multipart file parts from `DATA_UPLOAD_MAX_MEMORY_SIZE` — the file is
  received and spooled to a temp file *before* `apps.attachments.validators.validate_size`
  rejects anything over `MAX_ATTACHMENT_SIZE_BYTES` (10&nbsp;MB). Django has no built-in hard
  cap on multipart upload size; nothing in this application layer can reject an oversized file
  before it's fully received.

**Required reverse-proxy configuration**, not yet present anywhere in this repository (no
nginx/Caddy config is checked in — see "Deployment assumptions" above): the operator's reverse
proxy in front of `frontend` must cap request body size at the network layer, e.g. nginx's
`client_max_body_size 11m;` (slightly above `MAX_ATTACHMENT_SIZE_BYTES` so a legitimate
10&nbsp;MB upload's multipart framing overhead isn't itself rejected). Without this, an
oversized upload still gets rejected — but only after consuming bandwidth and temp disk space
receiving it, which matters for a public demo instance's disk/bandwidth budget more than it
would for a trusted-user internal deployment.

### Response headers

`frontend/next.config.ts` sends, on every response (HTML and static assets alike):
`Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `Referrer-Policy:
strict-origin-when-cross-origin`, `X-Frame-Options: DENY`, and a conservative
`Permissions-Policy`. The CSP allows `'unsafe-inline'` for both `script-src` and `style-src` —
this is a documented, verified-necessary trade-off (Next.js App Router's own React Server
Components hydration payload requires non-nonce'd inline `<script>` tags, and Recharts renders
inline `style` attributes for responsive SVG sizing), not a default reached without checking
the alternative. See the comment directly above the CSP definition in `next.config.ts` for the
full reasoning, including why a nonce-based policy was rejected (it would force this app's
currently-static routes into per-request dynamic rendering app-wide).

### Known development-only console warning: `eval()` blocked by CSP

Running `npm run dev` and opening the browser devtools shows a recurring `Console Error`
overlay: `eval() is not supported in this environment. If this page was served with a
Content-Security-Policy header, make sure that 'unsafe-eval' is included.` This is expected and
harmless — every page still renders and functions correctly around it. Do not "fix" it by adding
`unsafe-eval` to the CSP.

What's happening: React's development build uses `eval()` for some debugging features (e.g.
reconstructing component stack traces across module boundaries). `next.config.ts`'s `headers()`
applies the same CSP to every response regardless of `next dev` vs. `next build`/`next start`,
and that CSP has never included `unsafe-eval` (see the comment above the CSP definition — "No
unsafe-eval anywhere: production Turbopack output does not use eval()"), so React's dev-mode
`eval()` call is blocked and logged, exactly as the CSP is supposed to do.

Verified this is genuinely dev-only and not a build-output regression: `npm run build` (Turbopack
production build) completes cleanly, and every route was manually exercised end-to-end (filters,
mutations, comments/mentions, attachments, notifications) with no functional breakage from this
warning — the CSP's lack of `unsafe-eval` was never the thing gating any of that. If a
development-only relaxation is ever wanted, it must be explicit (e.g. `process.env.NODE_ENV
=== "development"` gating a separate, narrower dev CSP) and tested on its own — not folded into
an unrelated change.

## Attachment security model

Applies identically regardless of `QUORFIX_DEMO_MODE` — the public demo additionally tightens
`MAX_ATTACHMENT_SIZE_BYTES` (10 MB → 2 MB); see "Upload policy (public demo)" below for that and
for why uploads were kept enabled rather than disabled for demo personas.

- Content-type allowlist with no SVG (inline SVG can carry script — a stored-XSS vector) — see
  `backend/apps/attachments/validators.py`.
- Magic-byte / structural verification against the declared content type for every type that
  has a reliable signature (including verifying DOCX/XLSX are genuinely OOXML packages, not
  just any ZIP file relabeled).
- Path traversal prevention in the local storage provider (`backend/apps/attachments/
  providers.py`) — a storage key is always server-generated from a UUID, never derived from a
  client-supplied filename.
- Authenticated, organization-scoped download only; `Content-Disposition: attachment` (never
  inline) plus `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store` on
  every download response, so a browser is never invited to render an uploaded file inline in
  this application's own origin.
- Client-supplied display filenames are sanitized before storage and before being placed in
  the `Content-Disposition` header (control characters, path separators, and quote characters
  stripped) — never used to construct a filesystem path.
- Backup-archive restoration (see `docs/BACKUP_AND_RESTORE.md`) independently validates every
  tar member before extracting anything (`backend/apps/core/tar_safety.py`) — rejects absolute
  paths, `..` traversal, symlinks, and special/device files.
- **No malware/virus scanning exists in Community.** `backend/apps/attachments/scanning.py` is
  a documented extension point (a `MalwareScanner` Protocol a future Professional module could
  register) — Community ships no scanner and registers none. Format validation (above) is not
  malware scanning: a byte-signature-correct file can still carry a malicious payload for
  whatever application eventually opens it. If your threat model requires scanning uploaded
  files, do it at your reverse proxy or storage layer today; there is no Community-native
  alternative yet, and this document says so honestly rather than implying otherwise.

## Backup security

See `docs/BACKUP_AND_RESTORE.md` in full. Summarized:

- Backups are never written inside the repository, and never include `.env`.
- Every artifact in a recovery set (`database.dump`, `attachments.tar.gz`, `checksums.sha256`,
  `manifest.txt`) is written `chmod 600`; the recovery-set directory itself is `chmod 700`.
- A `database.dump` contains full application data, including account emails and comment
  content — treat it with the same sensitivity as the production database itself. Encryption
  at rest and off-site copies are the operator's responsibility; this project does not invent
  its own key-management scheme (see "Retention and encryption guidance" in
  `docs/BACKUP_AND_RESTORE.md`).
- Restoring from a backup requires an explicit `--confirm-restore` flag and independent
  checksum + manifest verification before anything is mutated — see that document's "Restore
  prerequisites."

## Known beta limitations

Documented honestly rather than left implicit:

- No independent third-party security audit has been performed.
- No malware/virus scanning of uploaded attachments (see above).
- `pip-audit`/`npm audit` findings are tracked and remediated on a best-effort basis (see
  [Dependency scan policy](#dependency-scan-policy)) — a clean scan today does not mean no
  vulnerability will ever be disclosed against a currently-pinned dependency version.
- No formal rate limiting on `comment`/`bug` creation — the audit backing this decision (see
  "Rate limiting" below) found no credible resource-exhaustion vector serious enough to justify
  it yet, but this is a judgment call, not an absolute guarantee, and may change.
- No CAPTCHA or bot-mitigation on public-facing endpoints (`/setup`, invitation accept) beyond
  the throttles listed below.
- Single-organization-per-installation is a Community *product* boundary (see `CLAUDE.md`),
  not itself a security boundary weakness, but it does mean Community has never been tested
  under the multi-tenant-per-installation shape Professional will eventually add.

### Rate limiting

Audited in Phase 6 Chunk G. Current throttle scopes
(`backend/config/settings/base.py`'s `DEFAULT_THROTTLE_RATES`):

| Scope | Rate | Why |
| --- | --- | --- |
| `login` | 10/min | Credential-stuffing/brute-force resistance. Shared with the demo-only `POST /api/auth/demo-login/` (see `docs/ACCESS_AND_TESTING.md` "Demo Quick Access (role login)") rather than giving it an independent budget. |
| `setup` | 3/hour | First-run instance setup — a one-time action per installation. |
| `setup-status` | 60/min | Cheap polling GET, loosely bounded. |
| `invitation-lookup` | 30/min | Public, unauthenticated token lookup. |
| `invitation-accept` | 10/min | Public, unauthenticated, mutates state. |
| `invitation-create` | 20/hour | Administrator-only, but sends email to an address the admin doesn't have to own — grouped with the other invitation endpoints rather than left unthrottled. |
| `attachment-upload` | 30/min | Shared by both halves of an upload (initiate + upload-bytes) — bounds how fast one account can fill the local attachment volume; generous enough for a normal multi-file drag-and-drop. |
| `membership-mutation` | 30/min | `PATCH`/`DELETE /api/members/{id}/` (role change, removal) — administrator-only but previously unthrottled; a genuine gap closed during the public-demo hardening pass (Community-wide, not demo-specific — role changes/removals are inherently rare administrative actions). |
| `demo-mutation` | 40/min | See "Public demo: blanket mutation throttle" below — inert (`None`, DRF's own "no rate configured" convention) unless `QUORFIX_DEMO_MODE=true`. |

Additionally, `POST /admin/login/` (Django's own admin, not a DRF view — the scopes above don't
cover it) is throttled separately by
`apps.core.middleware.admin_login_throttle.AdminLoginThrottleMiddleware`: 10 failed attempts per
5 minutes per client IP, using the same shared Redis cache. This is defense-in-depth, not the
primary control — in this project's actual deployment topology, `/admin/` is never proxied
through the public frontend at all (`frontend/next.config.ts` only rewrites `/api/*`, and
`docker-compose.prod.yml` never publishes the backend's port), so it is unreachable from the
internet by default regardless. It also grants no seeded account access: no `seed_demo`,
`seed_e2e_*`, or `/api/setup/`-created account is ever given `is_staff`/`is_superuser` — see
"Backend admin (Django) access" in `docs/ACCESS_AND_TESTING.md`.

**Deliberately not throttled** (for an ordinary Community installation): bug creation, comment
creation/editing, project creation. All were audited against the same disk/resource-exhaustion
concern as attachments and found not to warrant a per-endpoint scope — a spammed bug, comment,
or project is a small database row, not a multi-megabyte file, and normal legitimate use (bulk
triage, active discussion) can plausibly approach any conservative limit tight enough to matter
as abuse resistance. This is a considered decision, not an oversight, and it still holds for a
private, invite-only deployment — the abuse surface doesn't change based on who was invited.

### Public demo: blanket mutation throttle

The reasoning above assumes every user is either trusted (a real installation's own team) or was
individually vetted by an invitation (a private beta). Neither holds for the public demo, where
`QUORFIX_DEMO_MODE=true` lets an anonymous visitor authenticate instantly via Quick Access — so
the audited "not worth a per-endpoint scope" conclusion above no longer applies on its own.
Rather than reopening that per-endpoint audit (and risking new inconsistency for real
deployments), `apps.core.throttling.DemoMutationThrottle` adds one additional, demo-only safety
net: a 40/min-per-actor (authenticated user, or IP for the rare unauthenticated mutation) cap
applied to every mutating request site-wide, layered on top of (never replacing) the scoped
throttles above. Its `get_rate()` returns `None` — DRF's own convention for "this throttle does
nothing" — whenever `QUORFIX_DEMO_MODE` is false, which is every non-demo installation; the
Community-wide "deliberately not throttled" decision above is therefore completely unaffected
for real deployments. See `backend/apps/core/throttling.py`.

## Immutable demo personas

The five Quick Access personas (`docs/ACCESS_AND_TESTING.md` "Demo Quick Access (role login)")
are structural demo data, not visitor-owned accounts — the public demo would break for the next
visitor if one of them could be renamed, promoted, demoted, or removed by the visitor currently
using it. `apps.accounts.services.is_demo_user(user)` is the single, reusable, server-side check
(never a frontend state, never a role name or header the client supplies) that identifies one:
the account's email is one of the five allow-listed addresses *and* it holds a membership in the
organization slugged `quorfix-demo`.

Enforced in `apps.organizations.services` — never merely at the view/permission layer, so no
future endpoint can accidentally reach these records unprotected:

- `change_member_role` refuses if the target membership belongs to a demo persona — including an
  administrator-role demo persona changing its own role or a peer persona's, not only when it
  would leave the organization without an administrator (a separate, pre-existing guard).
- `remove_member` refuses the same way — a demo persona can never be removed via the API.
- `create_invitation` refuses entirely for the `quorfix-demo` organization — the public demo
  must never accumulate a sixth, real member (which would also mean sending email to an address
  the caller doesn't have to own; see "Mail sink" below).

Each raises `apps.organizations.services.ProtectedDemoAccountError`, which
`apps.organizations.views` turns into a generic `403 Forbidden` (`"This account cannot be
modified."` / `"Inviting new members is not available in this organization."`) — the response
never names "demo" or the protected email, so it reveals nothing an ordinary `IsOrganizationAdministrator`-only
403 wouldn't. There is one explicit, narrow bypass (`bypass_demo_protection=True`, a keyword-only
parameter), used by exactly one caller — `apps.core.management.commands.seed_demo`, the trusted,
operator-invoked tool that creates and reconverges these same five personas in the first place —
never reachable from any view, serializer, or HTTP request.

Out of scope for this mechanism because no such endpoint exists in Community today (confirmed by
direct code inspection, not merely by omission): there is no self-service way for any user,
demo persona or otherwise, to change their own email, username, password, or delete their own
account, and no API token / MFA feature exists to protect either (`api_tokens` and any MFA
concept are Professional-only, per `CLAUDE.md`'s edition boundaries, and neither is built yet).

## Mail sink (public demo)

Two places in Community trigger outbound email: `POST /api/invitations/` (an administrator
invites an address of their choosing — see `apps/organizations/views.py`) and Celery's
notification-email task (`apps/notifications/tasks.py`, always to an existing org member's own
address). The first is **fully attacker-controlled recipient** once reachable by an anonymous
Quick Access visitor with the demo's administrator persona — and is already closed entirely by
"Immutable demo personas" above (`create_invitation` refuses for the demo organization,
regardless of recipient). The second is lower risk (never an arbitrary address) but still
shouldn't reach real SMTP pointlessly from a shared public instance.

Defense in depth for both: when `QUORFIX_DEMO_MODE=true`, `EMAIL_BACKEND` is
`apps.core.mail.DemoMailSinkBackend` instead of the plain SMTP backend (see
`config/settings/production.py`) — a thin wrapper that still delivers over genuine SMTP (so
`apps.core.checks.check_email`'s production requirement for real delivery, `quorfix.E006`,
holds identically either way — this is deliberately *not* the locmem/console backend, which that
same check already rejects outright), but rewrites every message's `to`/`cc`/`bcc` to one
operator-controlled mailbox (`QUORFIX_DEMO_MAIL_SINK`) before sending, preserving the original
recipient in the subject line for operator visibility. `apps.core.checks.check_demo_mail_sink`
(`quorfix.E013`) fails startup if `QUORFIX_DEMO_MODE` is true and `QUORFIX_DEMO_MAIL_SINK` is
unset or implausible — a misconfigured sink can never silently fall through to real delivery.

**Result: no demo-triggered email can ever reach an arbitrary (or even a real member's) external
address.** Ordinary, non-demo installations are completely unaffected — `EMAIL_BACKEND` is the
plain SMTP backend exactly as before whenever `QUORFIX_DEMO_MODE` is false.

## Session lifetime (public demo)

Django's own default session lifetime (`SESSION_COOKIE_AGE`, two weeks) is unnecessarily long
for a throwaway, shared-browser demo exploration session. When `QUORFIX_DEMO_MODE=true`,
`SESSION_COOKIE_AGE` is shortened to 4 hours (override via
`QUORFIX_DEMO_SESSION_COOKIE_AGE_SECONDS`) — see `config/settings/base.py`. Every other cookie
security property (`Secure`, `HttpOnly`, `SameSite=Lax`) is unchanged either way. Ordinary
installations keep Django's default unmodified.

## Upload policy (public demo)

The existing attachment validation (content-type allowlist with no SVG, magic-byte/structural
verification, server-generated storage keys — see "Attachment security model" below) already
applies identically in demo mode; nothing about *what* is accepted changes. What does change:
`MAX_ATTACHMENT_SIZE_BYTES` drops from 10 MB to 2 MB when `QUORFIX_DEMO_MODE=true` (override via
`QUORFIX_DEMO_MAX_ATTACHMENT_SIZE_BYTES`) — a shared, anonymous-reachable instance has a much
smaller reasonable disk/bandwidth budget per upload than a trusted internal deployment. Uploads
were deliberately left enabled rather than disabled outright for demo personas: the existing
validation is already strong (see below), and attachments are a core, expected part of
demonstrating real bug-tracking workflows — disabling them would trade a large amount of product
demonstrability for a small additional risk reduction over the 2 MB cap. **Malware scanning
remains a documented Community gap regardless of demo mode** (see "Attachment security model")
and should be treated as a requirement for a future Professional/production-infrastructure
offering, not something Community — demo or otherwise — claims to provide today.

## Container resource limits

`docker-compose.prod.yml` previously set no memory, CPU, PID, or log-size limit on any service —
one abused or misbehaving container could consume unbounded host resources. Every service now
sets `mem_limit`, `cpus`, and `pids_limit` (plain Compose-spec keys, applied directly by `docker
compose up` — no Swarm/`deploy:` block involved, since this file is never deployed via `docker
stack deploy`), plus a shared, bounded `json-file` logging driver (10 MB × 3 files per
container, via the file's `x-logging` anchor):

| Service | Memory | CPUs | PIDs |
| --- | --- | --- | --- |
| `db` | 512m | 1.0 | 200 |
| `redis` | 256m | 0.5 | 50 |
| `backend` | 512m | 1.0 | 200 |
| `celery_worker` | 512m | 1.0 | 100 |
| `frontend` | 512m | 1.0 | 100 |

All overridable per-service via environment variables (`QUORFIX_<SERVICE>_MEM_LIMIT`/`_CPUS`/
`_PIDS_LIMIT`, `QUORFIX_LOG_MAX_SIZE`/`_MAX_FILES` — see `.env.example`) if a real host's
resources warrant something different; defaults apply equally to a real production deployment
and to the public demo, not only the latter. `celery_worker`'s concurrency was already
conservative before this pass (`CELERY_WORKER_CONCURRENCY`, default 2) and needed no further
change — see "Celery hardening" below.

## Celery hardening

Every demo-reachable code path that dispatches a Celery task goes through
`apps.notifications.tasks` (notification creation/email delivery) — there is no user-controlled
arbitrary task execution anywhere in Community (no endpoint accepts a task name or lets a client
choose what runs). Notification email is covered by the mail sink above regardless of demo mode.
Worker concurrency (`CELERY_WORKER_CONCURRENCY`, default 2 — see `docker-compose.prod.yml`) was
already conservative before this pass; retries use Celery's own default backoff, and no task in
this codebase performs unbounded work (attachment processing, exports, and "expensive analytics"
as commonly understood elsewhere do not exist in Community today — `apps/analytics` only ever
runs bounded, indexed read queries against the current organization's own data, all served
synchronously from the request, not via Celery).

## Redis hardening

Verified directly against `docker-compose.prod.yml`, not assumed: `redis` publishes no host
port, is reachable only from `backend`/`celery_worker` over the internal Compose network, and is
never proxied through the frontend. No `requirepass` is set by default — the network-only
exposure above is the primary control, consistent with this deployment's stated threat model (an
operator whose threat model needs it can add `--requirepass` via a `command:` override and switch
`REDIS_URL` to `redis://:<password>@redis:6379/0`, which the application already parses with no
code change). This is unchanged by the public-demo hardening pass — Redis was already correctly
isolated.

## PostgreSQL hardening

Also verified directly: `db` publishes no host port, credentials come entirely from
`POSTGRES_PASSWORD`/`POSTGRES_USER` (environment, never hardcoded — Compose itself refuses to
start if `POSTGRES_PASSWORD` is unset), and the schema/data volume persists normally across
restarts (`postgres_data`, untouched by `scripts/demo stop`/`restart` — see
`docs/DEMO_DEPLOYMENT.md`). The demo database user is the same single role every Community
deployment uses (no separate reduced-privilege role exists for any deployment shape yet); no
destructive reset exists anywhere in the lifecycle tooling shipped so far (`scripts/demo
reset-demo` is intentionally disabled — see `docs/DEMO_DEPLOYMENT.md` — pending a guarded,
purpose-built reset mechanism in a later release step).

## Logging hardening

Reviewed for accidental exposure of passwords, tokens, `Authorization`/cookie headers, SMTP
credentials, database URLs, uploaded file contents, and full request bodies — already covered by
the existing structured-logging design (`backend/apps/core/tests/test_logging_security.py`
exercises this directly) and unaffected by this pass: no new log statement introduced here logs
a request body, header, or credential (`DemoLoginView`/`DemoMailSinkBackend`/the membership and
invitation rejection paths above log only a fixed outcome string, the same posture as the
existing `LoginView`). Container log volume is now bounded regardless (see "Container resource
limits" above) — a broad security concern independent of what any individual log line contains.

## Edge / Cloudflare WAF (public demo)

**Status: DOCUMENTED, REQUIRES OPERATOR ACTION.** Nothing in this repository can configure
Cloudflare — no API token or account-specific configuration is or should ever be committed here
(see "Deployment assumptions"). The settings below are the concrete, current requirement for
whoever operates `demo.quorfix.com`'s Cloudflare zone; nothing here is a substitute for the
application-level controls elsewhere in this document (WAF is defense in depth — the application
itself must still correctly reject malicious input regardless of what Cloudflare blocks).

**Managed WAF**: enable Cloudflare's Managed Ruleset (and the OWASP Core Ruleset, if available on
the account's plan) for the demo hostname, in "block" (not merely "log") mode for `Critical`/
`High` severity findings.

**Bot protection**: enable Cloudflare's Bot Fight Mode (or Super Bot Fight Mode, if available) —
set to challenge, not block outright, so ordinary evaluators using a real browser are never
turned away; only clearly-automated traffic should be challenged.

**Rate limiting rules** (Cloudflare rules are IP-based, independent of and in addition to this
application's own per-user throttles above — a rotating-IP attacker who defeats one still hits
the other): create a rate-limiting rule for each of the following paths, all discovered directly
from `backend/config/urls.py`/`backend/apps/*/urls.py` (not assumed):

| Path | Suggested edge limit | Matches app-level scope |
| --- | --- | --- |
| `/api/auth/demo-login/` | 20 requests / 1 min / IP | `login` |
| `/api/auth/login/` | 20 requests / 1 min / IP | `login` |
| `/api/setup/` (POST) | 5 requests / 1 hour / IP | `setup` |
| `/api/invitations/*/accept/` | 20 requests / 1 min / IP | `invitation-accept` |
| `/api/bugs/*/attachments/` and `/api/attachments/*/upload-bytes/` | 60 requests / 1 min / IP | `attachment-upload` |

(There is no `/api/auth/password-reset/` in this codebase — Community has no self-service
password reset at all yet, see `docs/DEMO_DEPLOYMENT.md` §3 "Account recovery" — the row above is
listed as N/A rather than silently omitted, so this table doesn't imply it exists.)

**HTTP methods**: restrict `/admin/` to `GET`/`POST` only at the edge if a WAF custom rule is
available; do not restrict methods on `/api/*` broadly (`PATCH`/`PUT`/`DELETE` are legitimate
there).

**Admin routes**: `docker-compose.prod.yml` already never publishes the backend's port and
`frontend/next.config.ts` only rewrites `/api/*` (never `/admin/*`) through the public edge, so
`/admin/` is unreachable from the internet **by default, at the application/Compose level** —
this is the primary control, not an obscure URL. As additional, genuinely-recommended
defense-in-depth for a public demo specifically: put `/admin/` behind Cloudflare Access (or an
equivalent IP allowlist) at the edge as well, so a future accidental change to that
default-unreachable posture (e.g. a reverse-proxy misconfiguration) doesn't silently expose it.

**Origin protection**: only the `frontend` service's port may ever be reachable from the public
internet — confirmed directly against `docker-compose.prod.yml`: `db`, `redis`, `backend`, and
`celery_worker` publish no host port at all (see "Network exposure" in this document's own
audit trail, and `docs/DEMO_DEPLOYMENT.md`). The operator's reverse proxy/Cloudflare must route
*only* to the frontend's published port; never expose the backend, PostgreSQL, or Redis ports
directly, even for operational convenience.

## Dependency scan policy

- **Backend** (`pip-audit` against `backend/requirements.txt`, transitive dependencies
  included): runs in `.github/workflows/backend.yml`. Blocking when the scan is clean;
  non-blocking (with the full finding printed to the job summary, never silently discarded)
  when a finding requires a dependency upgrade outside the current change's scope, until that
  upgrade lands.
- **Frontend** (`npm audit --audit-level=high`): runs in `.github/workflows/frontend.yml`.
  Blocking whenever the baseline is clean (currently: 0 vulnerabilities at any severity).
- Neither scan is a substitute for prompt patching — a clean scan is a point-in-time result,
  re-evaluated on every CI run, not a standing guarantee.
