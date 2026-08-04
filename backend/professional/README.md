# Professional backend modules

Professional apps live here as ordinary Django apps (e.g. `professional.custom_fields`,
`professional.automation`). Each one:

- Is added to `INSTALLED_APPS` only when present and enabled — Community must run correctly
  with this directory empty.
- Registers its providers with the registries in `apps.core.registries`
  (`capability_registry`, `workflow_registry`, `analytics_registry`,
  `integration_registry`, `automation_registry`), typically from its `AppConfig.ready()`.
- Enforces its own capability/license check on every endpoint, service call, task, export,
  and integration it exposes. The backend is the source of truth for entitlement — Community
  code never imports from `professional.*` directly.
