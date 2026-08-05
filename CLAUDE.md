# Bug Fixer — Claude Code Instructions

## Product

Bug Fixer is an open-core bug-tracking platform.

Bug Fixer Community is free and open to small teams.

Bug Fixer Professional extends Community with advanced workflows, analytics, integrations, automation, licensing, and commercial support.

## Primary rule

Maintain one shared product.

Community must never import Professional modules.

Professional modules may extend Community interfaces, registries, services, providers, and extension points.

Community must remain fully functional when all Professional modules are absent or disabled.

Do not maintain separate copies of the same feature for Community and Professional.

## Technology stack

Frontend:

* Next.js App Router
* TypeScript with strict mode
* Tailwind CSS
* React Hook Form
* Zod
* TanStack Query
* Recharts
* Playwright

Backend:

* Python
* Django
* Django REST Framework
* PostgreSQL
* Redis
* Celery
* Pytest
* Ruff

Infrastructure:

* Docker
* Docker Compose
* S3-compatible object storage
* GitHub Actions

## Architecture

Build a modular monolith.

Do not introduce microservices unless the requirement cannot reasonably be handled by the modular monolith.

Organize backend code by domain:

* accounts
* organizations
* projects
* bugs
* comments
* attachments
* activities
* notifications
* workflows
* analytics
* integrations
* licensing

Keep:

* Business operations in service modules
* Complex reusable queries in selectors or query services
* API views and serializers thin
* Authorization on the backend
* External-service code behind provider interfaces
* Professional extensions behind registries and capabilities

Prefer extension registries:

* capability_registry
* workflow_registry
* analytics_registry
* integration_registry
* automation_registry

Avoid edition checks scattered throughout unrelated code.

## Edition boundaries

Community includes:

* Authentication
* One active organization per installation
* Standard roles
* Projects
* Bug creation and management
* Standard bug workflow
* Assignment
* Status, priority, and severity
* Comments
* Attachments
* Tags
* Watchers
* Basic activity history
* Basic dashboard
* Search
* Filters
* Basic notifications
* Core REST API
* Docker installation

Professional includes:

* Multiple organizations
* Custom roles
* Custom workflows
* Custom fields
* Saved views
* Advanced analytics
* Scheduled reports
* SLA tracking
* Automation rules
* API tokens
* Webhooks
* GitHub, GitLab, Slack, Teams, and Jira integrations
* SSO and SAML
* SCIM
* Audit exports
* AI assistance
* White labeling
* Commercial support tooling

Do not paywall essential bug creation, assignment, collaboration, search, filtering, or basic reporting.

## Capabilities

Professional functionality must be protected through backend capabilities.

Examples:

* multiple_organizations
* custom_roles
* custom_workflows
* custom_fields
* saved_views
* advanced_analytics
* scheduled_reports
* automation_rules
* sla_management
* api_tokens
* webhooks
* github_integration
* gitlab_integration
* slack_integration
* sso
* audit_export
* ai_assistance
* white_labeling

The backend is the source of truth.

Frontend capability checks improve the interface but do not provide authorization.

Every Professional endpoint, service operation, task, export, and integration must enforce its capability on the backend.

## Multi-tenancy

Every tenant-owned record must belong to an organization.

Every authenticated query must be scoped to the active organization.

Never trust organization identifiers supplied by the frontend without validating membership and authorization.

A user must never be able to read, search, update, delete, export, count, or infer another organization’s records.

Community may restrict an installation to one active organization, but the data model must remain organization-aware.

Cover tenant isolation with automated tests.

## Backend standards

* Use UUID primary keys.
* Use timezone-aware timestamps.
* Give bugs a separate human-readable identifier such as BUG-000123.
* Generate sequential identifiers safely under concurrent requests.
* Use database constraints where appropriate.
* Add indexes for commonly filtered and sorted fields.
* Use select_related and prefetch_related to prevent N+1 queries.
* Use atomic transactions for multi-record business operations.
* Validate workflow transitions.
* Use optimistic concurrency for frequently edited bug records.
* Return structured API validation errors.
* Use bounded server-side pagination.
* Never expose an endpoint that returns all bugs without a limit.
* Generate OpenAPI documentation.
* Record important changes through immutable activity records.

## Frontend standards

* Use server components by default.
* Use client components only for required interactivity.
* Keep API access in a dedicated typed API layer.
* Do not make API requests directly from arbitrary presentation components.
* Keep filters synchronized with URL search parameters.
* Provide loading, empty, no-results, error, unauthorized, and not-found states.
* Use accessible semantic HTML.
* Support keyboard operation.
* Provide visible focus states.
* Do not communicate status through color alone.
* Do not load the complete bugs dataset into the browser.
* Keep components focused and avoid duplicated interface logic.

## Security

* Use secure HTTP-only authentication cookies.
* Protect state-changing requests against CSRF.
* Validate authorization on every protected backend operation.
* Protect against insecure direct object references.
* Validate attachment size, content type, filename, organization, ownership, and access.
* Sanitize rendered user-generated content.
* Apply rate limits to sensitive operations.
* Do not log passwords, tokens, cookies, private keys, or attachment contents.
* Keep secrets outside source control.
* Encrypt sensitive integration credentials.
* Record security-relevant actions in the activity or audit log.

## Testing

For every feature, add the appropriate:

* Unit tests
* API integration tests
* Permission tests
* Tenant-isolation tests
* Capability tests
* Validation tests
* Concurrency tests
* Frontend component tests
* Playwright workflow tests

Every Community feature must be tested with Professional modules disabled.

Every Professional feature must be tested with:

* No license
* Missing capability
* Valid capability
* Expired or invalid entitlement where relevant
* Direct API invocation
* Cross-organization access attempts

## Working procedure

Before modifying code:

1. Inspect the repository.
2. Read relevant existing files.
3. Summarize the current implementation.
4. Identify the edition involved.
5. Identify affected modules.
6. Identify migrations.
7. Identify API changes.
8. Identify security risks.
9. Identify tenant-isolation risks.
10. Identify tests.
11. Propose a small implementation plan.

During implementation:

* Work in small, reviewable steps.
* Do not rewrite unrelated files.
* Preserve existing behavior unless the task explicitly changes it.
* Do not create placeholder production behavior.
* Do not leave required work as TODO comments.
* Do not silently change architecture.
* Do not add dependencies without explaining why.
* Update documentation when setup or behavior changes.

Before finishing:

1. Run formatting.
2. Run linting.
3. Run type checking.
4. Run relevant tests.
5. Inspect the final diff.
6. Report files changed.
7. Report commands executed.
8. Report test results.
9. Report migrations.
10. Report assumptions and unresolved risks.
11. Confirm Community still functions without Professional modules.

After completing any phase or chunk that changes routes, roles, credentials, demo data, setup
commands, or user-visible functionality: update `docs/ACCESS_AND_TESTING.md`, verify all
documented commands and URLs, and include the documentation update in the phase review.
