# Community Feature Freeze Policy

This document defines the frozen feature scope of Quorfix Community as of the `v1.0.0` release
audit, and what "frozen" does and does not mean going forward.

**Community is not abandoned.** The freeze means stable scope, not end-of-life. Community remains
a maintained, supported product.

## What the freeze means

Once `v1.0.0` is tagged, Community's product surface — the set of features described in
"Frozen Community feature set" below — does not grow through ordinary maintenance. This keeps
Community a coherent, predictable product rather than a moving target, and keeps the
Community/Professional boundary (see `CLAUDE.md`'s "Edition boundaries") meaningful over time.

## Community continues to accept

After `v1.0.0`, Community accepts:

- Security fixes
- Bug fixes
- Compatibility fixes (dependency, OS, browser, database version compatibility)
- Dependency maintenance (routine upgrades, vulnerability remediation)
- Documentation improvements
- Carefully scoped usability improvements that do not add new product surface (e.g. better
  empty/error states, accessibility fixes, performance improvements to existing features)
- Community contributions that fit within the frozen product boundary below

## Community does not automatically receive

- New commercial integrations (GitHub, GitLab, Slack, Teams, Jira, or similar)
- Enterprise identity features (SSO, SAML, SCIM)
- Advanced extensibility (custom roles, custom workflows, custom fields, an extension/plugin SDK)
- Licensing or entitlement features
- Premium automation (automation rules, scheduled reports, advanced analytics)
- Pro-only infrastructure or capabilities (webhooks, API tokens, audit export, white labeling,
  multi-organization support, AI assistance)

These are Professional roadmap candidates (see "Recommended Professional boundary" below). Adding
any of them to Community would require an explicit, separate decision to change this policy — not
a routine contribution or maintenance change.

## Frozen Community feature set

As verified during the `v1.0.0` release audit, Community includes:

**Authentication**
- Email/password login and logout
- Secure demo "Quick Access" role login (public demo environments only)
- Session-based authentication with secure, HTTP-only cookies

**Organizations**
- Single active organization per installation
- Organization membership management
- Standard roles (administrator, developer, QA, reporter, viewer) with backend-enforced
  permissions
- Invitations (create, look up, accept)

**Projects**
- Create, read, update, archive

**Bug/issue management**
- Create, read, edit
- Assignment
- Status, priority, severity
- Tags
- Optimistic concurrency on frequently edited records
- Bug relationships (where implemented)
- Human-readable identifiers (`BUG-000123` style)

**Comments and activity**
- Comments on bugs
- Immutable activity history

**Attachments**
- Upload, retrieve, delete
- Content-type, size, and organization/ownership validation

**Notifications**
- In-app notifications
- Email notifications, environment-appropriate (including a demo mail sink in public demo
  environments)
- Notification preferences

**Search and filtering**
- Bug/project search and filtering, synchronized with URL parameters
- Tenant-scoped results only

**Dashboard**
- Basic dashboard / recent-activity view

**API**
- Core REST API (Django REST Framework), OpenAPI-documented
- Bounded server-side pagination on every list endpoint

**Demo and operations tooling**
- Public demo lifecycle tooling (`scripts/demo`)
- Guarded, environment-checked demo reset
- Health checks
- Docker Compose installation (development and production)

This inventory reflects the CLAUDE.md "Edition boundaries → Community includes" list as actually
implemented in the codebase at the time of the `v1.0.0` audit; it is not a new scope decision.

## Recommended Professional boundary

Without implementing any of the following, the following capabilities are recommended Professional
roadmap items and should not be added to Community after the freeze:

- Multiple organizations per installation
- Custom roles, custom workflows, custom fields
- Saved views
- Advanced analytics, scheduled reports
- SLA tracking
- Automation rules
- API tokens, webhooks
- GitHub, GitLab, Slack, Teams, and Jira integrations
- SSO, SAML, SCIM
- Audit export
- AI assistance
- White labeling
- Commercial support tooling
- Multi-instance management
- Premium storage/infrastructure options

This list matches `CLAUDE.md`'s existing "Professional includes" section; it is restated here as
the freeze boundary, not a new decision. Final Community/Professional licensing and repository
boundaries are a separate decision (tracked as the project's next step) and are not made by this
document.

## Changing this policy

Community's frozen scope can change, but only through an explicit decision recorded as an update
to this document — never as a side effect of an unrelated bug fix, dependency upgrade, or
contribution. If a contribution would add new product surface beyond the frozen feature set above,
it belongs in a Professional module (see `CLAUDE.md`'s "Primary rule" on extension points), or
requires this policy to be revisited first.
