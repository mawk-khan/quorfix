# Security Policy

Quorfix Community is pre-1.0, beta software. This document describes what is and isn't
covered, how to report a vulnerability, and the security assumptions this project's
deployment model relies on. It is not a promise of response time, and it is not a complete
security audit — see [Known beta limitations](#known-beta-limitations) for what this document
does not claim.

**RELEASE BLOCKER: no monitored security contact exists yet (see [Reporting a
vulnerability](#reporting-a-vulnerability)).** A tagged public release must not ship until this
is resolved — see `docs/RELEASING.md`'s pre-release checklist, which treats this as a hard gate,
not an advisory note.

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

**RELEASE BLOCKER — placeholder contact.** No real, monitored security contact has been
configured. This repository's own configuration and Git remote metadata were checked
(Phase 6 Chunk K) specifically looking for an existing one — none was found. The address below
is a clearly-marked placeholder, not a functioning inbox; nothing in this repository invents or
assumes a real one:

```
security@REPLACE-ME-quorfix.example
```

A sensible real address, once the project owner has actually set it up, would be
`security@quorfix.com` — but that address must not be published here as if it works until the
owner confirms the mailbox (or forwarding rule) exists and is actively monitored. Until then:

- **Do not report a suspected vulnerability through a public GitHub issue.** This repository's
  issue templates (`.github/ISSUE_TEMPLATE/`) deliberately do not offer a "security" category for
  exactly this reason.
- Report a suspected vulnerability the same way you would reach a maintainer for anything
  sensitive — directly, privately, outside the public issue tracker — and say explicitly in the
  first line that it's a security issue.
- Hold technical/exploit details until you've reached a maintainer directly; see [What not to
  post publicly](#what-not-to-post-publicly).

**This project's release-readiness checklist (`docs/RELEASING.md`) will not be marked complete
while this section still describes a placeholder.**

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

## Attachment security model

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

- **No monitored security contact exists yet — this blocks a public release** (see [Reporting a
  vulnerability](#reporting-a-vulnerability)). Not merely undocumented; actively unresolved.
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
| `login` | 10/min | Credential-stuffing/brute-force resistance. |
| `setup` | 3/hour | First-run instance setup — a one-time action per installation. |
| `setup-status` | 60/min | Cheap polling GET, loosely bounded. |
| `invitation-lookup` | 30/min | Public, unauthenticated token lookup. |
| `invitation-accept` | 10/min | Public, unauthenticated, mutates state. |
| `invitation-create` | 20/hour | Administrator-only, but sends email to an address the admin doesn't have to own — grouped with the other invitation endpoints rather than left unthrottled. |
| `attachment-upload` | 30/min | Shared by both halves of an upload (initiate + upload-bytes) — bounds how fast one account can fill the local attachment volume; generous enough for a normal multi-file drag-and-drop. |

**Deliberately not throttled**: bug creation, comment creation/editing. Both were audited
against the same disk/resource-exhaustion concern as attachments and found not to warrant it
— a spammed bug or comment is a small database row, not a multi-megabyte file, and normal
legitimate use (bulk triage, active discussion) can plausibly approach any conservative limit
tight enough to matter as abuse resistance. This is a considered decision, not an oversight;
revisit it if real abuse is observed.

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
