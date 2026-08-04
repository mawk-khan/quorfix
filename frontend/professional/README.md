# Professional frontend modules

Professional UI (custom fields, advanced analytics, automation rules, integrations, SSO
setup, etc.) lives here. Components under this directory:

- Are only rendered when the backend reports the corresponding capability as enabled for
  the active organization.
- Never get imported by Community components directly — Community layouts render an
  extension slot and look up the Professional component through a registry, so the
  Community UI works unchanged when this directory is empty.
- Treat any capability check here as a UX convenience only. The backend remains the source
  of truth for authorization.
