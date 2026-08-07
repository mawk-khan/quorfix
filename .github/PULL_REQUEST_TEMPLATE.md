## Summary

<!-- What changed, and why. Link the issue this addresses if there is one. -->

## Edition

<!-- Community, Professional, or both. If Professional, confirm Community still works with it absent/disabled. -->

## Test plan

<!-- How you verified this. Check what applies; delete what doesn't. -->

- [ ] Backend: `ruff format`/`ruff check` pass
- [ ] Backend: `pytest` passes (new/changed behavior has test coverage)
- [ ] Frontend: `npm run lint` / `npm run typecheck` pass
- [ ] Frontend: `npm test` passes (new/changed behavior has test coverage)
- [ ] Playwright (`npm run test:e2e`), if this touches a user-facing flow
- [ ] Tenant-isolation coverage, if this touches a tenant-owned model or query
- [ ] `docs/ACCESS_AND_TESTING.md` updated, if this changes routes, roles, credentials, demo
      data, setup commands, or user-visible functionality (see CLAUDE.md's working procedure)

## Checklist

- [ ] I've read [CONTRIBUTING.md](../CONTRIBUTING.md) and [CLAUDE.md](../CLAUDE.md)
- [ ] This does not introduce a Community → Professional import
- [ ] No secrets, tokens, or credentials are included in this diff
- [ ] This is not a security vulnerability report (see [docs/SECURITY.md](../docs/SECURITY.md) if it is)
