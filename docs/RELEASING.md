# Releasing Quorfix

The procedure for cutting a tagged Quorfix Community release. **No release has been executed
yet** — this document describes the procedure, it does not claim one has happened. Do not
execute any step in this document without the project owner's explicit go-ahead.

## Pre-release checklist

All of the following must be true before tagging. Treat this as a gate, not a suggestion —
several items below are documented, tracked release blockers elsewhere in this repository.

1. **Update `VERSION`** (repository root) to the version being released — a plain semantic
   version, optionally with a prerelease suffix (e.g. `0.5.0-beta.1`). No `v` prefix in the file
   itself; the `v` prefix belongs on the Git tag only.
2. **Update `CHANGELOG.md`**: move the relevant `[Unreleased]` content (if any) into a new
   version section matching `VERSION` exactly, following Keep a Changelog structure. Fill in the
   actual release date once you're about to tag (not before — see that file's own convention of
   leaving it unset until publication).
3. **Run `scripts/check_version_consistency.sh`** — confirms `VERSION` is well-formed and that
   `CHANGELOG.md` has a matching heading.
4. **Full backend CI, locally or via a fresh push**: `make ci-backend` (Ruff, Django checks,
   migrations, full pytest suite, OpenAPI generation, Community-only isolation, `pip-audit` on
   both `requirements.txt` and `requirements-dev.txt` — both must be clean).
5. **Full frontend CI**: `make ci-frontend` (ESLint, TypeScript, Vitest, production build,
   `npm audit` — blocking at any severity).
6. **Full Playwright suite**: `npm run test:e2e` (frontend) or `make ci-e2e` (destructive to the
   local dev stack's current database — see `scripts/ci_e2e.sh`).
7. **Dependency audits are clean** — confirmed by steps 4–5 above; if either found a finding
   that requires an out-of-scope upgrade, that upgrade must land (or the finding must be
   explicitly accepted and documented, per `docs/SECURITY.md` "Dependency scan policy") before
   proceeding.
8. **Documentation review**: `scripts/check_docs.sh` (see [Documentation link/branding
   validation](#documentation-linkbranding-validation) below) passes — no broken relative links,
   no stray old-repository URLs, no leftover pre-rename branding, no placeholder URL
   presented as real.
9. **Security contact verified** — `docs/SECURITY.md`'s "Reporting a vulnerability" section must
   describe a real, monitored contact, not the placeholder. **This is the current release
   blocker** as of this writing; do not proceed past this step until the project owner confirms
   the contact is live.
10. **Code of Conduct contact verified** — same requirement, `CODE_OF_CONDUCT.md`'s
    "Enforcement" section.
11. **Production image build**: `make ci-images` (builds both production images fresh, verifies
    non-root runtime users, minimal container smoke check — never pushes).
12. **Clean-install drill**: follow `docs/INSTALLATION.md`'s "Clean-install smoke test" against
    a genuinely fresh environment (no reused volumes) end to end.
13. **Upgrade drill**: if this is not the first release, follow `docs/UPGRADING.md` against a
    copy of the previous version's data — confirm migrations apply cleanly and
    `scripts/upgrade_smoke.sh` passes.
14. **Backup/restore drill**: `docs/BACKUP_AND_RESTORE.md`'s disposable restore drill — take a
    backup, restore it into a disposable environment, confirm the application actually works
    against the restored data.
15. **Accessibility checklist**: the relevant section of `docs/ACCESS_AND_TESTING.md`'s manual
    test checklist, plus a clean `npx playwright test e2e/accessibility.spec.ts` run.
16. **Release notes drafted** — see [Release notes](#release-notes) below.

Do not tag until every item above is either done or explicitly, knowingly waived by the project
owner with the reason recorded (e.g. in the tracking issue for the release).

## Tagging and the release workflow

1. Commit the `VERSION` and `CHANGELOG.md` changes from steps 1–2 above.
2. Tag the commit: `git tag v$(cat VERSION)` (e.g. `v0.5.0-beta.1`).
3. Push the tag: `git push origin v$(cat VERSION)`.

Pushing the tag triggers `.github/workflows/release.yml`, which:

1. **`validate-tag`** — confirms the tag matches `vX.Y.Z[-prerelease]` and equals `v$(cat VERSION)`
   exactly (reading `VERSION` from the tagged commit itself). A mismatch fails the workflow
   before anything is built.
2. **`backend-checks`** / **`frontend-checks`** — the *entire* `backend.yml`/`frontend.yml`
   workflows, invoked via `workflow_call`, run again against this exact tagged commit. A release
   is not built from a commit that hasn't passed full CI.
3. **`build-and-push`** (only after both checks jobs succeed) — builds
   `ghcr.io/<owner>/quorfix-backend:vX.Y.Z` and `ghcr.io/<owner>/quorfix-frontend:vX.Y.Z` from
   the tagged commit, verifies non-root runtime users and a minimal smoke check against the
   *actual images about to be pushed* (not a separately-built `:ci` copy), pushes both to GHCR
   using the workflow's own `GITHUB_TOKEN` (no long-lived credential, nothing embedded in the
   workflow file), and records both images' digests in the job summary.

`<owner>` resolves to the actual GitHub repository owner (`mawk-khan`, once this repository is
hosted there) automatically — nothing in the workflow hardcodes it.

## Image naming

| Component | Local build tag | Published tag |
| --- | --- | --- |
| Backend | `quorfix-backend:${VERSION:-local}` | `ghcr.io/mawk-khan/quorfix-backend:vX.Y.Z` |
| Frontend | `quorfix-frontend:${VERSION:-local}` | `ghcr.io/mawk-khan/quorfix-frontend:vX.Y.Z` |

`docker-compose.prod.yml` builds and uses the local tags by default; point it at a published
GHCR tag instead by overriding the `image:` field (e.g. via an additional `-f` override file)
rather than editing the file in place.

## After the release

1. **Record image digests** — already done automatically in the workflow's job summary (step 3
   above); copy them into the release notes for a tamper-evident reference.
2. **Publish release notes** — a GitHub Release against the pushed tag, using the
   [Release notes](#release-notes) content below.
3. **Post-release smoke test** — pull the *published* images (not a local build) and repeat
   `docs/INSTALLATION.md`'s clean-install smoke test against them, to prove what was actually
   published works, not just what was built locally.
4. **Rollback decision** — if the smoke test fails, do not attempt to fix forward under the same
   tag (tags must be immutable once published). Either:
   - Leave the previous tag as the recommended version and fix forward under a new tag, or
   - If the failure is severe and already-deployed, follow `docs/UPGRADING.md`'s rollback
     procedure to return affected deployments to the previous version's image tags — Git tags and
     GHCR image tags are never force-moved/overwritten to "fix" a bad release in place.

## Release notes

Draw directly from `CHANGELOG.md`'s entry for this version — do not duplicate its content by
hand, link/quote it. Include:

- The version and release date.
- A short summary of what's new (from `CHANGELOG.md`'s "Added" section).
- Known beta limitations (from `CHANGELOG.md`'s "Known beta limitations" section) — every
  release notes post repeats these until they're actually resolved, not just for the first one.
- The image digests recorded in the release workflow's job summary.
- Upgrade instructions (link to `docs/UPGRADING.md`) if this is not the first release.

## Documentation link/branding validation

`scripts/check_docs.sh` (see that script's own header) checks every relative Markdown link
resolves, that GitHub links point at `mawk-khan/quorfix`, that domain references point at
`quorfix.com`, and that no leftover pre-rename branding or placeholder URL remains. Run it
as part of step 8 above; it's read-only and safe to run anytime.
