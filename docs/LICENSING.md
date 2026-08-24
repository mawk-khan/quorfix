# Licensing

This document states the licensing facts for Quorfix. It does not contain, and must never
contain, proprietary commercial contract text — see "Legal review checklist" below for what
belongs in a separate, non-public agreement instead.

## Quorfix Community

**License: Apache License 2.0.** Full text in [`LICENSE`](../LICENSE) at the repository root.
Third-party dependency licenses are tracked separately in
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

**Decision: Community retains Apache-2.0.** Evaluated against the project's actual goals:

| Requirement | Apache-2.0 |
| --- | --- |
| Genuinely open-source Community edition | Yes — OSI-approved, permissive |
| Commercial proprietary Professional edition alongside it | Yes — Apache-2.0 imposes no obligation on separately-licensed code that merely depends on it |
| Third parties may use/fork Community | Yes, under the license terms (attribution, NOTICE-forwarding, stating changes) |
| Patent grant | Yes — explicit patent grant in §3, with a defensive termination clause (§3) if a licensee sues over patent infringement |
| Building proprietary software on top | Yes — Apache-2.0 does not require derivative or combined works to be released under the same license (contrast: copyleft licenses like AGPL/GPL, or "source available" licenses with a Commons Clause-style restriction) |
| Clear NOTICE/attribution obligations | Yes — §4 defines them precisely (retain copyright/patent/trademark notices, state changes, include the License text) |
| No requirement that proprietary extensions become open source | Confirmed — this is exactly why Apache-2.0, not a copyleft license, fits the open-core model |

No competing requirement was found that Apache-2.0 fails to meet. Changing it would weaken
Community's open-source credibility for no corresponding benefit — the commercial boundary this
project needs belongs in a *separate* Professional license, not in restricting Community's.

```text
Should Quorfix Community retain Apache License 2.0?

YES
```

**No fake "open core" license was invented for this decision**, and none should be, absent a
concrete, specific legal or business reason not present here. No Commons Clause, SSPL-style
restriction, non-commercial clause, or source-available restriction was added to Community's
license in this step. Community is intended to remain genuinely open source; commercial
restrictions belong entirely in Professional's separate license, never layered onto Community's.

**Legal review flag:** this analysis is an engineering/product read of a well-known, standard OSS
license's terms, not legal advice. Confirm with counsel before a commercial launch that this
reading holds for the specific combination of Community (Apache-2.0) plus a proprietary
Professional product depending on it, particularly regarding patent grant scope and any
third-party Apache-2.0-licensed dependency whose own NOTICE obligations must be forwarded (see
"NOTICE file" below).

## Quorfix Professional

**Model:** commercial, proprietary license — not Apache-2.0, not any other OSS license — living in
a **separate, private repository** (`quorfix-pro`, not yet created; see
`docs/EDITION_BOUNDARIES.md` §2).

**Community code obligations inside Professional:** Professional does not become Apache-2.0-licensed
merely by depending on or extending Community — Apache-2.0 places no such "inherit our license"
requirement on separate works that use it (unlike a copyleft license). However, this only holds
cleanly if Professional *depends on* Community rather than *copies* it:

- **Prefer dependency/extension.** Professional imports Community's public extension surface
  (registries, documented service hooks, the REST API) or, at a lower level, depends on a released
  Community artifact/tag (see `docs/EDITION_BOUNDARIES.md` §14 "Packaging"). This is the model
  the whole edition-boundary architecture in that document is built around.
- **If a Community file is ever copied directly into the Professional repository** (which this
  architecture is designed to avoid, and which the "prefer dependency" rule above exists
  specifically to prevent), that copied file remains subject to its original Apache-2.0
  obligations — copying does not launder the license. Professional's own proprietary code sitting
  alongside it does not need to be Apache-2.0, but the copied file itself still does, and still
  needs its original copyright/attribution notices retained per Apache-2.0 §4. This is a real risk
  only if the "prefer dependency, don't copy" rule is violated — it should not be, and no current
  plan calls for it.

**Proprietary code status:** Professional source code is proprietary and confidential to Quorfix.
It is not open source, is not dual-licensed, and is not made available under any OSS license.

**Repository visibility:** private, restricted developer access. Recommended baseline controls
(not created in this step — recorded as requirements for whoever provisions the repository):
branch protection on the default branch, mandatory code review before merge, CI on every change,
secret scanning enabled, **no license-signing private key ever committed to the repository**
(see `docs/EDITION_BOUNDARIES.md` §13), tagged releases, and dependency pinning against specific
compatible Community version ranges (§12 of that document).

**Commercial agreement required:** yes — a customer-facing EULA/commercial license agreement is a
Step 6 "must exist before commercial launch" item, drafted by counsel, and it is explicitly **not**
drafted here (see "Legal review checklist" below). This document states the *fact* that
Professional is separately, commercially licensed; it is not, and must never become, that
agreement's text.

## NOTICE file

Apache License 2.0 §4(d) requires forwarding an existing `NOTICE` file's attribution content when
one exists in a work being redistributed — it does not require inventing a `NOTICE` file where
none is warranted. Quorfix Community:

- Does not itself ship a `NOTICE` file, and none is required for Quorfix's own original
  source — there is no upstream Quorfix `NOTICE` to forward, since Quorfix is not a fork or
  derivative of another Apache-2.0 project.
- Already documents third-party dependency attributions in
  [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md), which serves the practical purpose a
  `NOTICE` file would, without the formal Apache-2.0 `NOTICE`-file mechanics being triggered (no
  reviewed dependency in `requirements.txt`/`requirements-dev.txt`/`package.json` was found to
  ship its own `NOTICE` file requiring forwarding at this audit's depth of review).

**Result: no `NOTICE` file is required at this time.** Revisit if a future dependency is added that
ships its own Apache-2.0 `NOTICE` file — that would need forwarding into a genuine `NOTICE` file at
that point, not before.

## Package metadata

Fixed as part of this step, now that Apache-2.0 is confirmed for Community:

- `backend/pyproject.toml` — added a minimal `[project]` table declaring
  `license = "Apache-2.0"` (SPDX expression). No `version` field was added: this file has no
  `[build-system]` table and is not used to build/publish a Python package (the backend is deployed
  as a Django application in a container, not distributed via PyPI), so inventing a duplicate
  version source here would create exactly the kind of drift already flagged and deliberately
  avoided for `frontend/package.json` in `docs/RELEASING.md` (the repository-root `VERSION` file is
  the single source of truth).
- `frontend/package.json` — added `"license": "Apache-2.0"`. Its existing `"version": "0.1.0"` is
  unrelated npm package metadata, not the product version, and is intentionally not synchronized
  with the root `VERSION` file (unchanged in this step — see `scripts/check_version_consistency.sh`,
  which does not check `package.json`, by design).

## Legal review checklist

Real, concrete items requiring professional legal review **before a commercial Professional
launch**. None of these block Community `v1.0.0` tagging — Community's own license (Apache-2.0) is
clear and unambiguous today.

- Final Quorfix Professional commercial EULA / license agreement text.
- Warranty and liability disclaimer terms for Professional, beyond whatever Apache-2.0 already
  disclaims for Community (Apache-2.0 §7/§8 disclaim warranty and limit liability for Community
  itself, but a commercial agreement for Professional needs its own terms).
- Trademark policy — "Quorfix" naming/logo usage rules for community forks, integrations, and any
  third party referencing the product.
- Privacy policy — required once any hosted service (the public demo today; a future Professional
  cloud/hosted offering) processes personal data.
- Terms of service for the hosted public demo and any future hosted/cloud Professional offering.
- A Data Processing Agreement (DPA), if Professional is ever offered as a hosted service handling
  customer data subject to GDPR/CCPA or similar regimes.
- Export/compliance review if Professional (particularly signed-licensing cryptography, per
  `docs/EDITION_BOUNDARIES.md` §13) is distributed to jurisdictions with export-control
  requirements on cryptographic software.
- Third-party integration terms — API terms of service for GitHub, GitLab, Slack, Teams, and Jira
  integrations (Professional roadmap items) must be reviewed before those integrations ship,
  since each platform's own developer/API terms govern what a Quorfix integration may do.
- Commercial support agreement terms (SLA commitments, support tiers), if Professional includes a
  paid support offering as `CLAUDE.md`'s Professional feature list anticipates.

None of the above is drafted in this step. This checklist exists so Step 7 (tagging) and Step 8
(Professional foundation work) know what remains outstanding and why it does not block either.
