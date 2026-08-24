# Community / Professional Edition Boundaries

This document is the single reference for how Quorfix Community and Quorfix Professional
("Pro" is used as an informal shorthand for the same edition in casual discussion; this document
and the rest of the codebase use "Professional" as the canonical name — see `CLAUDE.md`) relate to
each other: licensing, repository ownership, dependency direction, extension points, and version
compatibility. It records decisions, not proposals — later sections state what future Professional
work (Step 8 onward) must respect.

Nothing in this document changes Community's frozen `v1.0.0` feature scope — see
`docs/COMMUNITY_RELEASE_POLICY.md` for that. This document defines the boundary Professional
grows behind, not what Professional will contain.

## 1. The invariant

```text
Community must NEVER import Professional.
Professional MAY depend on and extend Community.
```

This holds for Python imports, Django app registration, frontend imports, migrations, API
contracts, build tooling, packaging, tests, and deployment. Concretely:

- The Community test suite runs with `professional/` empty.
- The Community Docker stack (`docker-compose.yml`, `docker-compose.prod.yml`) runs with
  `professional/` empty.
- Community migrations apply with no Professional app installed.
- The Community frontend builds with `frontend/professional/` empty.
- Community CI (`.github/workflows/backend.yml`, `frontend.yml`) never requires Professional
  code, secrets, or a license.

This is already enforced today, not merely aspirational: `apps/*/tests/test_community_isolation.py`
(9 tests, run in `scripts/ci_backend.sh`) assert that none of the five registries have any
provider registered when Professional is absent, and a `test ! -f professional/apps.py` check in
the same script fails CI outright if a Professional app is ever accidentally committed into the
public repository.

## 2. Repository architecture

**Decision: two physically separate repositories, not a branch or a subdirectory-with-restricted-history.**

```text
PUBLIC   — github.com/mawk-khan/quorfix   ("quorfix")
  Quorfix Community: backend, frontend, API contracts, Community tests,
  Community Docker setup, docs, extension interfaces (registries, contracts)

PRIVATE  — quorfix-pro (to be created; not created in this step)
  Quorfix Professional: Professional backend apps, Professional frontend
  modules, license verification, premium integrations, enterprise features,
  Professional tests, Professional deployment/release tooling
```

Rationale: physical repository separation is the actual security boundary. A private branch in
the public repo, or committing-then-removing proprietary code before a public push, both leave
proprietary source recoverable from Git history or reflogs — neither is acceptable. Two
repositories with independent access control is the only model that matches "Community can be
maintained indefinitely without access to the private Professional repository."

`quorfix-pro` is **not created in this step** — Step 6 only decides the model.

### Remote strategy (existing)

Community currently pushes to two remotes: `origin` (`github.com/mawk-khan/quorfix`, public,
primary) and an internal `bitbucket` working/backup remote (not publicly documented here by URL —
it is not part of Community's public identity).

**Decision: Bitbucket remains an internal backup/working remote, not an official public Community
mirror.** GitHub (`origin`) is the single public source of truth referenced by documentation,
issue tracking, and the release workflow (`docs/RELEASING.md`'s tag/push/GHCR flow is GitHub-only).
Nothing changes about this in Step 6 — recorded here so the distinction is explicit rather than
assumed.

## 3. Dependency direction

```text
Community ← Professional
```

Forbidden in Community code, everywhere, permanently:

```python
from professional import something
from quorfix_pro import something
```

Allowed in Professional code:

```python
from apps.core.registries import capability_registry, workflow_registry
```

or an equivalent documented Community contract import. Professional depends on Community; the
reverse is never permitted, checked in CI (`test_community_isolation.py` suite), and enforced
structurally: Community modules have no Professional package to import even at import-resolution
time in a Community-only checkout, since `professional/` ships empty.

## 4. Extension-boundary assessment (existing registries)

Five registries already exist in `backend/apps/core/registries.py`, all built on one shared
`Registry` class (`register`/`unregister`/`get`/`is_registered`/`keys`):

| Registry | Current consumers in Community | Coupling | Suitable as Professional seam? |
| --- | --- | --- | --- |
| `capability_registry` | `apps.organizations.policies` (`multiple_organizations`), `apps.attachments.services` (`malware_scanning`) | Low — Community reads `is_registered()`/`get()` and treats an absent key as "not available," never raises | Yes, already working as designed |
| `workflow_registry` | `apps.bugs.workflow` (`WORKFLOW_PROVIDER_KEY`) | Low — same get-or-None pattern | Yes |
| `analytics_registry` | None yet (no consumer in Community code) | None | Yes, unused but ready |
| `integration_registry` | None yet | None | Yes, unused but ready |
| `automation_registry` | None yet | None | Yes, unused but ready |

Observations:

- **Initialization model**: module-level singletons instantiated at import time in
  `apps/core/registries.py`. A Professional app registers into them from its own
  `AppConfig.ready()` — standard, well-understood Django extension timing (after all apps are
  loaded, before requests are served).
- **Error isolation**: `register()` raises `ValueError` on a duplicate key (fails loud at startup,
  not at request time), but `get()`/`is_registered()` never raise for an absent key — this is the
  correct shape for "Community stays fully functional when Professional is absent." No consumer in
  Community currently wraps `.get()` calls in error handling because none is needed by design.
- **Public API surface**: intentionally minimal (5 methods, no metadata beyond key→provider).
  Sufficient for the "is this available, give me the implementation" pattern; not yet expressive
  enough for provider metadata (versioning, per-organization enablement beyond what
  `capability_registry` consumers already do at the call site).
- **Community dependency on external implementation**: none. Every current registry consumer
  degrades to documented, tested Community-only behavior when nothing is registered
  (`malware_scanning` absent → no scan performed, documented in `docs/SECURITY.md`;
  `multiple_organizations` absent → single-active-org constraint enforced).
- **No release-blocking defect found.** No rewrite recommended.

### Additional extension interfaces needed later (Step 8+, not built now)

- An **event/hook mechanism**. Today, Community has no signal or event bus — activity recording
  (`apps.activities.services.record_bug_activity` and similar) is called directly, inline, from
  each mutation's service function. This is sufficient for Community's own audit trail but is not
  a subscribable extension point. Professional automation, integrations, analytics, and AI
  features will need one. Candidate events, based on `docs/COMMUNITY_RELEASE_POLICY.md`'s frozen
  feature set: `bug.created`, `bug.updated`, `bug.status_changed`, `bug.assigned`,
  `comment.created`, `project.created`, `project.archived`, `member.invited`, `member.role_changed`,
  `attachment.added`. Not built in Step 6 — a release-blocking-sized decision belongs in Step 8's
  "extension interfaces" foundation work, not here.
- A **frontend registry/extension-slot mechanism**. `frontend/professional/README.md` already
  documents the intended shape (Community renders an extension slot, looks up a Professional
  component through a registry, never imports it directly) but it is not implemented — no
  Community component currently renders such a slot, and no frontend registry exists yet (see
  §6 below). This is a real gap for Step 8, not a Step 6 defect, since no Professional frontend
  code exists yet to plug into it.

## 5. Backend boundary

**Community owns:** core domain models and apps (accounts, organizations, projects, bugs,
comments, attachments, activities, notifications, workflows, analytics — the Community-scope
implementation only), the Community REST API, `apps.core.registries`, the `apps/integrations` and
`apps/licensing` **contract/scaffolding** apps (see §9), Community migrations, Community Docker
setup, Community tests.

**Professional owns:** Professional Django apps (illustrative future names:
`professional.custom_fields`, `professional.automation`, `professional.integrations_github`,
`professional.licensing`, `professional.sso`), their own migrations, their own tests, license
verification, premium integration providers.

### Django app loading strategy

**Decision:** Community's `INSTALLED_APPS` (in `backend/config/settings/base.py`) never references
Professional apps by name, and Community never contains `try: import professional_x except
ImportError` scattered anywhere. Instead, Community adds one explicit, controlled extension point:

```python
# backend/config/settings/base.py (illustrative — not built in Step 6)
INSTALLED_APPS = [
    ...,  # fixed Community app list, unchanged by Professional's presence
]
INSTALLED_APPS += getattr(settings, "QUORFIX_EXTRA_DJANGO_APPS", [])
```

A Professional deployment supplies its own settings module that imports Community's and extends
it:

```python
# professional's own settings module (lives in the Professional repo, not here)
from config.settings.production import *  # noqa: F403

INSTALLED_APPS += [
    "professional.custom_fields",
    "professional.automation",
]
```

This keeps the extension point singular and explicit (one settings variable, one place it's
consumed) rather than edition-detection conditionals spread through the codebase. Not implemented
in Step 6 — this section records the intended pattern for whoever builds the Step 8 foundation.

### Migration dependency direction

**Decision, matching the invariant:**

- Community migrations belong only to Community apps and never depend on a Professional
  migration.
- Professional migrations belong only to Professional apps, and may declare a dependency on a
  Community migration (e.g. a Professional model with a `ForeignKey` to `bugs.Bug` depends on
  the Community migration that created that table) — this is the normal, expected direction.
  it is never reversed.
- Professional never forks or copies Community's migration files into the Professional
  repository, and never modifies Community's migration history.

### Data model boundary

**Decision:** new Professional capabilities get their own tables related to Community entities by
foreign key, rather than nullable Professional-only columns added onto Community models. Example
pattern (illustrative, not built): `ProjectSLAConfiguration`, `ProjectAutomationPolicy`, and
`ProjectIntegrationConfig` as separate Professional-owned models with a `project = ForeignKey(
"projects.Project")`, instead of adding `sla_target`, `automation_policy_id`, etc. directly onto
Community's `Project` model. This keeps Community's schema clean, keeps Professional's migrations
self-contained, and means Community continues to work — including its own migrations — whether or
not Professional's tables exist. No exception to this pattern has been identified during this
audit; if one is found during actual Professional implementation, it should be documented there,
not assumed here.

## 6. Frontend boundary

**Community owns:** the whole Next.js application today — routes, navigation, the typed API
client layer, all rendered UI. **Professional owns (future):** UI modules under
`frontend/professional/`, which — per that directory's own README — are meant to be rendered only
through a registry lookup behind a backend-reported capability, never imported directly by
Community components.

**Current state:** this pattern is documented but not implemented. `frontend/professional/`
contains only a README; no Community component currently renders an extension slot, and no
frontend equivalent of `apps.core.registries` exists. This is a known gap, not a defect — there is
no Professional frontend code yet to justify building the wiring.

**Gaps identified for Step 8:**

- A frontend capability/registry module (conceptually mirroring the backend's `Registry` class)
  that Community components can query (`getCapabilityComponent("advanced_analytics")`) without
  importing anything Professional-specific.
- Concrete extension-slot components in the places Professional will need them: navigation
  (adding a nav item), the dashboard (adding a widget), settings pages (adding a settings section),
  and bug/project detail views (adding a panel — e.g. SLA status).
- A capability-flag pattern already exists conceptually on the backend (`Session`-object fields
  like `demo_mode`, echoed from settings, never a build-time `NEXT_PUBLIC_*` value — see Step 5's
  frontend audit). The same "backend tells the frontend what's available; the frontend never
  decides for itself" pattern should extend to Professional capabilities: the session/bootstrap
  API response should carry an `enabled_capabilities: string[]` (or similar) field once
  Professional capabilities exist, so the frontend has one source of truth to query rather than
  guessing from a `NEXT_PUBLIC_*` env var or a hardcoded edition flag.

None of this is built in Step 6.

## 7. Avoiding edition conditionals

**Decision:** neither the backend nor frontend should be designed around
`if settings.IS_PRO` / `if (isPro)` conditionals scattered through Community code. The existing
pattern (`capability_registry.is_registered("multiple_organizations")`,
`capability_registry.get("malware_scanning")`) is correct and should be the only pattern used
going forward: Community asks "is this capability available," never "which edition is this."
Community code has no reason to know the word "Professional" exists.

## 8. Capability model vs. license entitlement

These are related but distinct, and must not be collapsed into one check:

```text
Community capability exists          → always available, no registry involved
Professional capability registered   → the implementation is installed (Professional app present)
License entitlement                  → the customer is permitted to use that implementation
```

A capability being *registered* (Professional app installed) is necessary but not sufficient for
it to be *usable* — that also requires a valid license entitlement. **Decision:** license
verification does not belong coupled into every domain model or scattered through Community
service functions. It belongs in Professional's own layer, sitting between "capability is
registered" and "the actual feature runs" — conceptually:

```text
license document → signature verification → entitlement service → capability resolver → Professional feature
```

Community's registries (`capability_registry`, etc.) only ever answer "is a provider registered."
They are not, and should not become, the place license validity is decided. That keeps Community
free of any licensing awareness at all, matching §13 below.

## 9. Integration boundary — `backend/apps/integrations` decision

Community's `apps.integrations` and `apps.licensing` currently exist only as empty `AppConfig`
scaffolding (verified during the Step 5 audit: no models, no views, no URLs, not referenced
anywhere else in the codebase beyond `INSTALLED_APPS`). This matches `CLAUDE.md`'s own backend
domain list, which already names `integrations` and `licensing` as Community-organized domains.

**Decision: Option A.** Community keeps integration *contracts* and the `integration_registry`
seam; actual integration providers (GitHub, GitLab, Slack, Teams, Jira, and any future ones) live
in Professional. Concretely, going forward:

- `apps.integrations` may eventually hold shared, edition-agnostic pieces: a stable `Provider`
  protocol/interface, webhook-signature-verification helpers usable by any provider, and the
  `integration_registry` consumer wiring — but never a specific vendor's implementation.
- `apps.licensing` may eventually hold the entitlement/capability-resolution *interface* Community
  exposes (so Professional's license verifier has something documented to plug into), never the
  license verifier itself.
- Nothing precludes a genuinely open-source, community-maintained integration appearing in
  Community later (Option C) if one is ever proposed and it doesn't require paid infrastructure —
  but none is planned, and this is not a Step 6 commitment to build one.

This is a policy decision, not an implementation — nothing in `apps.integrations`/`apps.licensing`
changes in this step.

## 10. API boundary

**Decision:** Community does not adopt a blanket `/api/pro/` prefix for branding's sake. Community
owns `/api/*` as it exists today. When Professional endpoints are added later, each uses whichever
URL is cleanest for its domain — e.g. `/api/analytics/advanced/` rather than
`/api/pro/analytics-advanced/` — with the deciding rule being **domain semantics, not marketing.**
Structurally:

- Community's `backend/config/urls.py` never imports a Professional URLconf.
- A Professional installation extends the root URL configuration from its own settings/urls module
  (the same "import Community's, then add to it" pattern as §5's `INSTALLED_APPS` strategy), so
  Community's URL configuration is unaware Professional URLs exist.

### API authentication / webhook boundary

Community already exposes session-cookie-based REST API authentication sufficient for the
Community frontend and any first-party script using the same session. **Decision:** basic
programmatic API usability stays in Community — the REST API itself, its OpenAPI schema, and
session-based auth are not paywalled. What's Professional is the *advanced* programmatic-access
layer: durable API tokens/service accounts, fine-grained scoped tokens, and webhooks (outbound
event delivery to third parties). This matches `CLAUDE.md`'s existing "Do not paywall essential
bug creation, assignment, collaboration, search, filtering, or basic reporting" principle applied
to the API specifically — the API remains usable, but long-lived unattended credentials and
outbound webhook delivery are Professional infrastructure investments, not Community-core.

## 11. Community API stability (what Professional may rely on)

| Layer | Stability | Professional may depend on it |
| --- | --- | --- |
| `apps.core.registries` (`capability_registry`, `workflow_registry`, `analytics_registry`, `integration_registry`, `automation_registry`) | Public extension API | Yes |
| Domain service-layer functions explicitly intended as extension hooks (e.g. `apps.bugs.workflow`'s provider lookup) | Public extension API | Yes |
| REST API endpoints and their documented request/response contracts (OpenAPI schema) | Public extension API | Yes, as a normal API consumer |
| Everything else in `apps/*/services.py`, `apps/*/selectors.py`, internal helper functions | Internal API | No — may change between Community releases without notice |
| Private/underscore-prefixed functions, view internals, serializer internals not part of the documented API | Unstable/private implementation | No |

Not every internal function is a stable contract. Professional development must go through a
registry, a documented service-layer hook, or the public REST API — never reach into Community's
internals directly, even though physically nothing stops it before repository separation exists.

## 12. Version compatibility policy

**Decision:** Community and Professional version independently (both follow semantic versioning),
and Professional declares an explicit supported Community version range rather than assuming
lockstep or pinning to a Git commit hash.

```text
Community: v1.0.0, v1.0.1, v1.1.0, ...
Professional: v1.0.0, v1.0.1, v1.1.0, ...  (independent numbering)
```

Professional's own release metadata states something like
`"compatible_community_range": ">=1.0.0,<2.0.0"`, checked at Professional startup (a system check,
mirroring Community's existing `apps.core.checks` pattern) rather than assumed silently. Versions
may track broadly release-to-release without being required to move in exact lockstep forever —
a Community patch release (`v1.0.1`, security/bug fix) should not force an immediate matching
Professional release unless the fix actually affects a contract Professional depends on.

## 13. Licensing architecture direction (for Step 8 — not built now)

- **Community never requires a license.** No license check exists anywhere in Community code
  today, and none should be added — Community must build, install, and run with zero awareness
  that commercial licensing exists.
- **If Professional is absent:** Community functions normally (already true today).
- **If Professional is installed but the license is invalid or absent:** Community's own
  functionality is unaffected; only Professional-gated capabilities become unavailable, per a
  policy Step 8 will define precisely (see `docs/LICENSING.md` §"Failure policy direction" for the
  intended shape). A licensing problem in Professional must never be able to "brick" Community's
  core.
- **Signed license direction:** the vendor signs a license document with a private key kept only
  in controlled vendor licensing infrastructure; the application ships only the corresponding
  public verification key and verifies signatures locally. The private signing key must never
  exist in the Community repository, the Professional repository, any Docker image, any customer
  installation, or any frontend bundle.
- **Offline verification:** self-hosted installations verify a signed license locally; Quorfix's
  servers being unreachable must not block a self-hosted customer's Professional features from
  continuing to work within the license's validity window. Periodic online re-validation may be an
  optional future business policy, not a hard requirement designed now.
- **License payload (candidate fields, not finalized):** `license_id`, `customer_id`,
  `customer_name`, `issued_at`, `expires_at`, `edition`, `entitlements` (capability list),
  `max_users` (if usage-based), `license_version`, `signature`. Deliberately avoid binding tightly
  to unstable machine/hardware identifiers, since self-hosted deployments need to survive
  container restarts, VM migration, and disaster-recovery restores without re-licensing.
- **None of the above is implemented in Step 6.** This section exists so Step 8 starts from an
  agreed direction instead of re-litigating it.

## 14. Event/hook, CI, packaging, and deployment direction (summary)

These are elaborated in full in the relevant sections above and in this document's companion,
`docs/LICENSING.md`; summarized here for a single point of reference:

- **CI boundary:** Community CI never requires the Professional repository, Professional secrets,
  a commercial license, or a private package — already true today (`.github/workflows/backend.yml`,
  `frontend.yml` run entirely from public Community code). A future Professional CI pipeline would
  check out a compatible tagged Community release, build/install the Professional extension on top
  of it, run Community's own test suite as a compatibility smoke check, then run Professional's own
  tests, licensing tests, and integration tests.
- **Packaging (initial strategy):** for early Professional development, the simplest workable
  approach is a **source/tag dependency** — the Professional repository's CI and local dev checks
  out a specific compatible Community Git tag (not a floating branch, not a bare commit hash) and
  builds against it. This avoids inventing a package registry or artifact repository before there
  is more than one consumer of Community as a dependency. **Future scaling strategy:** if
  Professional (or third-party extensions) grow enough to need faster iteration or independent
  versioning of individual Community interfaces, revisit packaging Community's stable extension
  surface (the registries and any published API client) as versioned internal packages. Not needed
  now — do not build this in Step 6 or prematurely in Step 8.
- **Deployment composition:** a Community deployment is exactly what exists today
  (`docker-compose.prod.yml`: backend, frontend, PostgreSQL, Redis, Celery). A Professional
  deployment composes on top of that — Community's core services, plus Professional backend/
  frontend extensions (loaded via the `QUORFIX_EXTRA_DJANGO_APPS`-style mechanism in §5 and a
  Professional-specific frontend build), plus licensing, plus any optional integration
  worker/service Professional needs — rather than a wholly separate parallel infrastructure stack.

## 15. Explicit non-goals reaffirmed for this step

- No fake "open core" license was invented; Community remains under a standard, recognized OSS
  license (Apache-2.0 — see `docs/LICENSING.md`). No Commons Clause, SSPL-style, non-commercial,
  or source-available restriction was added to it.
- No existing Community `v1.0.0` feature was reclassified as Professional. "Multiple
  organizations" (§16) and "API tokens/webhooks" (§10 above) were the two areas Step 5 flagged as
  needing care; both are resolved below without narrowing anything Community already ships.

### Multiple organizations — precise scope

Community's organization *data model* already supports multiple organizations structurally (every
tenant-owned record belongs to an organization; the schema is organization-aware, per
`CLAUDE.md`'s multi-tenancy section). What Community restricts, by design, is **an installation
being limited to one active organization** — a deliberate Community simplification, not a data
model limitation. **Decision:** "multiple organizations" as a future Professional capability means
premium multi-organization *management* — a single installation hosting several active
organizations, with the cross-organization administration UX, org-switching, and
org-provisioning workflow that implies — not "the ability for the schema to represent an
organization" (which Community already has and always will, since every tenant-owned model
requires it). This does not touch Community's existing single-active-organization behavior or its
underlying schema in any way.

## Files this document does not cover

Proprietary commercial contract terms (EULA, support agreements, pricing) never belong in this
public repository — see `docs/LICENSING.md`'s "Legal review checklist" for what still needs
drafting elsewhere, by counsel, before a commercial launch.
