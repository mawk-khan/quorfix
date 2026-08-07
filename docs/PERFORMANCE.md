# Performance: dataset generation, measurement, and findings

## 1. Scope

Community-only. Covers a safe, development-only method to generate
realistic-scale data (`generate_perf_dataset`), a read-only measurement tool
(`measure_performance`), the results collected against a local reference
environment, and the two evidence-based optimizations those results
justified.

This is **not** a capacity plan, a load test, or a production benchmark —
see "Known limitations" (§16) before drawing any conclusion beyond "this is
what a single request costs locally, on this hardware, on this dataset."

## 2. Safety warnings

Read this before running anything in this document against a real database.

- `generate_perf_dataset` refuses to run at all unless `BUGFIXER_DISPOSABLE_DATABASE=true`
  is set in the environment for that one invocation. This variable exists
  *only* to gate this command — never set it in `.env`, never set it against
  a database you use for anything else.
- It additionally refuses under production settings, if the configured
  database name looks like a production database, or if the target database
  already contains the `seed_demo` organization or either E2E fixture
  organization.
- The `--full` (~100,000-bug) profile requires **both** `--full` and
  `--confirm-disposable-database` — the two flags are independent and both
  required; neither is inferred from `DEBUG` or from
  `BUGFIXER_DISPOSABLE_DATABASE` alone.
- Cleanup (`--cleanup-existing-perf-data`) requires the same
  `--confirm-disposable-database` flag, prints exactly what it is about to
  delete, and is scoped — by an assertion checked immediately before every
  delete, not just by construction — to organizations whose slug starts with
  `perf-`. It never issues a bare `TRUNCATE` and never resets a global
  sequence.
- `measure_performance` is read-only (it never writes or deletes application
  data) and is not gated behind `BUGFIXER_DISPOSABLE_DATABASE` for that
  reason, but it authenticates as a real user and issues real requests, so
  point it at the same disposable database you generated data into.

Every number in this document was produced against a disposable PostgreSQL
container created solely for this exercise (`quorfix_perf_test`, a
throwaway `postgres:16-alpine` container on a separate Docker volume, joined
to the project's own `bug-fixer_default` network — docker-compose.yml's own
Compose project name is deliberately unrenamed, see that file's own comment)
— never against the project's own development database, and never against
production.

## 3. Dataset profiles

| | Default | Full |
|---|---|---|
| `--organizations` | 1 | 5 |
| `--projects-per-organization` | 5 | 20 (100 total) |
| `--users-per-organization` | 10 | 50 (250 total) |
| `--bugs-per-organization` | 1,000 | 20,000 (100,000 total) |
| `--comments-per-bug` (average) | 1.5 | 1.5 |
| `--activities-per-bug` (average) | 3.0 | 3.0 |
| `--notifications-per-user` (average) | 15.0 | 15.0 |
| `--attachment-rate` | 0.1 | 0.1 |

Every count is overridable independently; `--full` only changes the
defaults the un-overridden arguments resolve to (see
`generate_perf_dataset.py`'s `DEFAULT_PROFILE`/`FULL_PROFILE`).

## 4. Generation commands

```bash
# Small, safe default — always start here.
BUGFIXER_DISPOSABLE_DATABASE=true \
  docker compose exec backend python manage.py generate_perf_dataset

# Full ~100,000-bug dataset — slow (~2.5 minutes locally), needs both flags.
BUGFIXER_DISPOSABLE_DATABASE=true \
  docker compose exec backend python manage.py generate_perf_dataset \
  --full --confirm-disposable-database

# Cleanup — deletes every perf-owned organization and nothing else.
BUGFIXER_DISPOSABLE_DATABASE=true \
  docker compose exec backend python manage.py generate_perf_dataset \
  --cleanup-existing-perf-data --confirm-disposable-database
```

Or via `make perf-seed-small`, `make perf-seed-full-confirm`,
`make perf-clean-confirm` (§19).

**Ownership marker**: organization slugs start with `perf-`, user emails end
in `@perf.invalid`, project keys start with `PERF`, and every bug's
`created` activity carries `{"perf_dataset": true, "seed": <seed>}` in its
`metadata`.

**Where this bypasses the real service layer**: `generate_perf_dataset` uses
`bulk_create` in batches rather than `apps.bugs.services.create_bug` and
friends — those each take a row lock and commit individually, which is
correct for real traffic and far too slow for 100,000 bugs. Every place this
happens, and exactly how the equivalent invariant is reconstructed by hand
(sequential bug numbering, `resolved_at`/`closed_at` rules, the
comment-required notification constraint, the attachment status/timestamp
constraint), is documented in the command's own module docstring and at each
function that does it — see `generate_perf_dataset.py` directly rather than
duplicating that explanation here.

## 5. Generated distributions

From a real `--full --seed 100` run:

```
Performance dataset generated.
  organizations: 5
  users: 250
  memberships: 250
  projects: 100
  bugs: 100000
  activities: 300000
  comments: 264600
  mentions: 39536
  attachments: 12951
  notifications: 1091
  elapsed: 153.4s

Generated bug status distribution:
  in_progress: 14726 (14.7%)
  triaged: 12986 (13.0%)
  assigned: 12965 (13.0%)
  resolved: 11243 (11.2%)
  new: 10857 (10.9%)
  reopened: 7658 (7.7%)
  ready_for_qa: 7323 (7.3%)
  blocked: 5740 (5.7%)
  deferred: 3685 (3.7%)
  duplicate: 3656 (3.7%)
  closed: 3610 (3.6%)
  cannot_reproduce: 2784 (2.8%)
  wont_fix: 2767 (2.8%)
```

Against the Chunk I target shape: open statuses (in_progress + triaged +
assigned + new + ready_for_qa + blocked + deferred) = 68.3% (target 65-75%);
resolution statuses (resolved + duplicate + cannot_reproduce + wont_fix) =
20.4% (target 15-25%); closed = 3.6% (small, as intended); reopened = 7.7%
(target 5-10%). All within the requested ranges.

## 6. Reference environment

| | |
|---|---|
| CPU | 16 allocated container CPUs |
| RAM | 15 GiB |
| Docker | 28.4.0 |
| PostgreSQL | 16.14 (postgres:16-alpine) |
| Redis | 7.4.10 |
| Python | 3.12.13 |
| Django | 5.1.15 |
| Dataset | full profile, seed 100 — 100,000 bugs / 5 orgs / 300,000 activities / 264,600 comments |
| Database size | 321 MB (with the two new indexes from §11; 291 MB before) |
| Cache state | Redis warm/cold as noted per scenario; cold means cache cleared immediately before *every* measured request, not just once before the run |
| Runs / warmup | 15 measured runs, 2 warmup runs, per scenario (`--runs 15 --warmup-runs 2`) |

**These are local reference results, not a production capacity guarantee** — see §16.

## 7. Measurement methodology

`measure_performance` authenticates as a real administrator member of a
chosen perf-owned organization via Django's test-client session login (no
password ever printed or logged), then issues real requests through
`rest_framework.test.APIClient` against the real DRF views — the same URL
routing, permission classes, selectors, and serializers a browser request
would hit. Network transport is the only thing not represented, which is
the point: it isolates application/database performance from local network
variability (§16).

For each scenario: `--warmup-runs` unmeasured requests (skipped entirely for
`cold`-cache scenarios, where a warmup request would prime exactly the
cache being measured around), then `--runs` measured requests, each wrapped
in `django.test.utils.CaptureQueriesContext` to record every query and its
individual time. Reports median/min/max duration (p95 only once
`--runs >= 20`, this document's runs are 15), response status and byte
size, query count, and total captured SQL time.

```bash
docker compose exec backend python manage.py measure_performance \
  --organization perf-001 --runs 15 --warmup-runs 2 --include-sql \
  --output /tmp/measure.json
```

## 8. Results (full dataset, 20,000 bugs in the measured organization)

All times in milliseconds, median of 15 runs.

| Scenario | Median | Min | Max | Queries | SQL time |
|---|---:|---:|---:|---:|---:|
| bugs-first-page | 30.7 | 28.7 | 31.9 | 5 | 21.0 |
| bugs-project-filter | 4.9 | 4.7 | 6.9 | 4 | 0.0 |
| bugs-status-filter | 24.5 | 21.8 | 44.5 | 5 | 15.0 |
| bugs-assignee-filter | 12.1 | 11.5 | 14.3 | 5 | 4.0 |
| bugs-search (after §11) | 17.0 | 16.2 | 21.3 | 5 | 8.0 |
| bugs-max-page-size | 39.4 | 36.8 | 68.2 | 5 | 23.0 |
| bugs-deep-page (page 500) | 98.7 | 97.0 | 121.6 | 5 | 90.0 |
| bug-detail | 10.2 | 9.7 | 12.6 | 8 | 3.0 |
| bug-activity | 7.8 | 7.6 | 8.3 | 7 | 3.0 |
| bug-comments (hottest bug) | 11.5 | 10.8 | 14.0 | 9 | 2.0 |
| bug-attachments | 6.6 | 6.2 | 7.0 | 6 | 1.0 |
| notifications-first-page | 4.2 | 3.8 | 5.3 | 4 | 0.0 |
| notifications-unread-only | 4.1 | 3.8 | 33.3 | 4 | 0.0 |
| notifications-unread-count | 3.0 | 2.9 | 3.2 | 4 | 0.0 |
| projects-list | 6.9 | 6.1 | 9.5 | 5 | 1.0 |
| project-detail | 4.2 | 4.0 | 6.0 | 4 | 1.0 |
| members-list | 6.4 | 5.7 | 7.9 | 5 | 1.0 |
| analytics-summary-cold | 26.0 | 22.2 | 32.8 | 7 | 20.0 |
| analytics-summary-warm | 2.8 | 2.6 | 3.7 | 3 | 0.0 |
| analytics-summary-redis-unavailable | 24.7 | 22.9 | 31.2 | 7 | 18.0 |
| analytics-trends (cold) | 23.3 | 21.9 | 25.0 | 5 | 18.0 |
| analytics-resolution-time (cold, after §11) | 6.2 | 5.6 | 7.2 | 4 | 2.0 |
| analytics-distributions (cold) | 19.1 | 17.1 | 20.8 | 5 | 14.0 |
| analytics-workload (cold) | 13.8 | 13.0 | 16.1 | 5 | 8.0 |
| analytics-active-projects (cold) | 32.0 | 30.8 | 36.9 | 4 | 27.0 |
| analytics-recent-activity (never cached) | 50.8 | 49.4 | 56.1 | 5 | 43.0 |

Small-profile (1,000 bugs) numbers were also collected and are consistently
under 20ms across every scenario except `bugs-deep-page`, which 404s at
that scale (only 40 pages exist) — see §13.

## 9. Query counts

Every scenario stays at a small, bounded query count (4-9) regardless of
dataset size — confirms §1's audit finding that `select_related`/`Exists()`
annotations already prevent N+1 behavior across bug list/detail, comments,
attachments, notifications, projects, and memberships. No scenario's query
count grew between the 1,000-bug and 100,000-bug datasets. The full
project-level `pytest` suite's own existing query-count assertion tests
(`apps/*/tests/test_query_counts.py` and friends) all still pass after both
optimizations in §11 (995 passed, 1 skipped — no query-count regressions).

## 10. EXPLAIN findings

Captured via `queryset.explain(analyze=True, buffers=True)` against the
real selector functions, on the full 100,000-bug dataset (organization
`perf-001`, 20,000 bugs).

### Bug search (`title__icontains` / `key__iexact` / `key__icontains`), before

```
Bitmap Heap Scan on bugs_bug (actual time=0.390..11.767 rows=735 loops=1)
  Recheck Cond: (organization_id = '25a7f1bc...'::uuid)
  Filter: ((archived_at IS NULL) AND ((upper((title)::text) ~~ '%CHART%'::text)
           OR (upper((key)::text) = 'CHART'::text)
           OR (upper((key)::text) ~~ '%CHART%'::text)))
  Rows Removed by Filter: 19265
Execution Time: 13.308 ms
```

Every one of the organization's 20,000 bugs is fetched and filtered
row-by-row — no index serves the substring match. `icontains`/`iexact`
compile to `UPPER(col) LIKE UPPER(pattern)` on this database (not native
`ILIKE`), which matters for what kind of index can actually serve it — see
§11.

### Deep page (`?page=500`, offset 12,475)

```
Limit (actual time=85.159..85.512 rows=25 loops=1)
  -> Nested Loop Left Join (actual time=46.375..54.733 rows=12500 loops=1)
       -> Gather Merge (actual time=46.140..49.280 rows=12500 loops=1)
            -> Sort (actual time=29.253..29.993 rows=4167 loops=3)
                 Sort Method: external merge  Disk: 7744kB
```

PostgreSQL must materialize and sort **all** 14,035 matching rows (spilling
to disk — `external merge`) before it can discard the first 12,475 and
return 25. This is the well-known cost of `OFFSET`-based pagination: no
index lets it skip straight to row 12,475 of a joined, filtered, sorted
result set. See §13 — not fixed in this chunk, documented as future work.

### Recent activity (organization-wide, no project filter)

```
Index Scan using activities__organiz_069dbe_idx on activities_bugactivity
  (actual time=0.065..0.069 rows=29 loops=1)
  Index Cond: (organization_id = '25a7f1bc...'::uuid)
Execution Time: 1.229 ms
```

Confirms §15: PostgreSQL **does** choose the Phase 5
`(organization, -created_at)` composite index at this scale for the actual
row-fetch — the 50.8ms measured end-to-end in §8 is not this query; it is
DRF's separate pagination `COUNT(*)` query on the same join (see §16).

### Resolution activity (`resolved_bug_count`/trends/resolution-time), before

```
Bitmap Heap Scan on activities_bugactivity (actual time=0.550..4.743 rows=1854 loops=3)
  Recheck Cond: (organization_id = '25a7f1bc...'::uuid)
  Filter: ((created_at >= ...) AND ((verb)::text = 'status_changed'::text)
           AND ((to_value)::text = ANY ('{...}'::text[])))
  Rows Removed by Filter: 18146
Execution Time: 19.686 ms
```

No index covers `verb`/`to_value` — every request that isn't a cache hit
scans and filters the organization's full activity history. See §11/§15.

## 11. Optimizations

Two changes, both meeting every gate in §13 of the Chunk I spec (measurable,
representative dataset, safe, before/after evidence, existing tests still
pass):

### a) `pg_trgm` trigram indexes on `Bug.title` and `Bug.key`

Migration `bugs/0003_bug_search_trigram_indexes.py` enables the `pg_trgm`
extension (`TrigramExtension()` — a standard PostgreSQL contrib extension,
present on this project's own `postgres:16-alpine` image and any managed
PostgreSQL 12+ offering) and adds two `GIN` indexes on `UPPER(title)` and
`UPPER(key)` — matched to the exact expression Django's `icontains`/`iexact`
already compile to on this database, confirmed by testing the SQL directly
against a real PostgreSQL instance before relying on it (Django 5.1's
auto-generated `AddIndex(GinIndex(OpClass(...)))` SQL for this construct
turned out to have a syntax bug — missing parens around the expression —
so the migration uses `RunSQL` with the corrected SQL and a matching
`state_operations` block instead).

`retain current search semantics` (§11's own requirement): no query or
serializer code changed at all — `apps.bugs.selectors.list_bugs`'s `search`
filter is untouched. The index alone changes the plan.

**Before → after** (search for `"chart"`, 20,000-bug organization):

```
Before: Execution Time: 13.308 ms  (full scan + row filter, 19,265 rows removed)
After:  Execution Time: 4.750 ms   (BitmapOr across both trigram indexes)
```

~2.8x faster at 20,000 bugs/org, and — unlike the "before" plan — this stays
roughly flat as the table grows further, since it no longer scales with
organization size the same way a full filter scan does.

### b) `BugActivity` composite index + a query fix on `_base_resolution_activity`

Migration `activities/0006_bugactivity_activities_verb_lookup_idx.py` adds
`(organization, verb, to_value, created_at)` — covering exactly the filter
`apps.analytics.selectors._base_resolution_activity` (backing
`resolved_bug_count`, `trends`, and any post-cache-miss recompute) already
applies.

The index alone was not sufficient — and demonstrates why "before/after
evidence" matters rather than reasoning from the index alone:

```
Index added, no query change: Execution Time: 42.898 ms  (WORSE than before: 19.686 ms)
```

Making the `BugActivity` side of the join cheaper caused the planner to
switch strategies for the `Bug` side too — from a `Nested Loop` doing 5,563
cheap indexed point-lookups into `bugs_bug`, to a `Hash Join` built from a
full sequential scan of **all 79,899** non-archived bugs across every
organization (not just this one), because nothing in the query gave the
planner an organization-scoped predicate on `bugs_bug` directly. Adding
`bug__organization=organization` to the selector — redundant with the
already-present `organization=organization` filter on `BugActivity` (a
`BugActivity`'s bug always belongs to the same organization, by
construction) but newly *usable* by the planner — fixed it:

```
Index + bug__organization filter: Execution Time: 14.061 ms
```

Net: 19.686 ms → 14.061 ms (~29% faster), and confirmed via the real
`apps.analytics.selectors._base_resolution_activity` function itself, not a
hand-rolled approximation.

### Not changed

- `recent_activity`'s own row-fetch already uses the Phase 5 index correctly
  (§10) — no index or query change applied.
- No new denormalization, no materialized view, no background
  precomputation, no external search service — none were justified by the
  evidence, and all are explicitly out of scope for this chunk regardless.

## 12. Before/after evidence

Summarized from §11 — both re-run against the real selector/queryset
functions, same organization, same 100,000-bug dataset, `EXPLAIN ANALYZE`
each time:

| Query | Before | After | Change |
|---|---:|---:|---:|
| Bug search (`"chart"`) | 13.3 ms | 4.8 ms | -64% |
| Resolution activity (30-day window) | 19.7 ms | 14.1 ms | -29% |

## 13. Deep-page findings

`?page=500` (offset 12,475 of ~14,035 matching rows) took 98.7ms median at
the full dataset — the slowest first-class scenario measured, dominated by
an on-disk external sort over every matching row before the requested page
can be sliced out (§10). **Not fixed in this chunk** — page-number
pagination is unchanged, per Chunk I's explicit instruction not to replace
it. Cursor (keyset) pagination — ordering by `(created_at, id)` and
filtering `WHERE (created_at, id) < (last_seen_created_at, last_seen_id)`
instead of counting offsets — is the standard fix and is recorded here as
future work. It would benefit `GET /api/bugs/` most directly, and similarly
benefits any other page-number-paginated, potentially-deep endpoint in this
codebase (comments/attachments on an unusually active bug; notifications).
It is a breaking response-shape change (opaque cursor tokens instead of
page numbers) and was correctly out of scope here.

## 14. Search findings

Confirmed via source inspection (§1 audit) and `EXPLAIN`: `list_bugs`'s
`search` parameter used plain `icontains`/`iexact` — no PostgreSQL
full-text search, no trigram matching, before this chunk. Measurably slow
at 20,000 bugs/org (13.3ms, scaling with organization size). Fixed with the
smallest justified change: two `pg_trgm` `GIN` indexes (§11a), zero query or
semantics changes. `pg_trgm` was chosen over PostgreSQL full-text search
because it directly accelerates the *existing* substring-match semantics
(`icontains`) without changing what "search" means to a user (full-text
search tokenizes/stems, which is a materially different, arguably better,
but different feature) — matching §11's explicit instruction to "retain
current search semantics where possible."

## 15. Cache findings

- **Cold** (cache cleared immediately before every request): summary 26.0ms,
  trends 23.3ms, distributions 19.1ms, workload 13.8ms, active-projects
  32.0ms, resolution-time 6.2ms — all comfortably under the 1-second target
  (§17) even before considering caching at all.
- **Warm**: summary 2.8ms — roughly 9x faster than cold, confirming the
  cache avoids all selector/database work on a hit (`apps.analytics.caching.
  cache_or_compute` returns the cached value directly with zero additional
  queries — 3 queries on both cold and warm measured runs are session/auth
  overhead, not analytics work).
- **Redis unavailable**: simulated via `override_settings(CACHES=...)`
  pointed at an unreachable port. `analytics-summary-redis-unavailable`
  still returned `200` with correct data (24.7ms, i.e. compute-directly
  cost, not an error) — confirms `cache_or_compute`'s try/except-around-both-
  read-and-write fallback works end to end, not just in isolation.
- **Isolation**: cache keys are already `organization_id`+project+date-range
  scoped (`apps.analytics.views`, confirmed by source read, not re-derived
  here) — no cross-tenant leak risk introduced or found.
- **TTL**: left at 60 seconds — no evidence in this exercise justified
  changing it.
- **Recent activity**: confirmed still uncached (§8's `analytics-recent-
  activity` scenario has no cache-mode variants because there is nothing to
  cache).

## 16. Known limitations

- **These results are not a capacity guarantee.** They describe one request
  at a time, on one machine, against one generated dataset shape.
- **Local network latency is not represented.** `measure_performance` calls
  Django views in-process via `APIClient` — no TCP, no TLS, no reverse
  proxy, no real browser.
- **Concurrent-user testing is limited to none.** Every measurement here is
  strictly sequential, one request at a time. Lock contention (e.g. the
  `Project.next_bug_number` row lock in `create_bug`), connection-pool
  exhaustion, and cache-stampede behavior under concurrent load are not
  covered.
- **Real attachment storage and transfer throughput are not covered** — the
  performance dataset deliberately generates metadata-only, never-uploaded
  `Attachment` rows (`status=failed`, no physical file — see the generator's
  own docstring); this document says nothing about actual file upload/
  download throughput.
- **Backup/restore timing is separate from request performance** — see
  `docs/BACKUP_AND_RESTORE.md`, not this document.
- **`analytics-recent-activity`'s pagination `COUNT(*)` query was found to
  be the dominant cost** (40ms of its 43ms total SQL time) — DRF's default
  pagination counts the full filtered/joined queryset separately from
  fetching the page. Still well under the 1-second target, so no change was
  made; flagged here as a candidate for a future, similarly-scoped
  investigation (the same `bug__organization`-style query fix from §11b may
  apply, but this was not verified with EXPLAIN and is explicitly not
  claimed).
- **p95 was not computed for the results in §8** — 15 runs is below this
  project's own `measure_performance --runs 20` threshold for a p95
  figure to be meaningful; only median/min/max are reported.
- The two new indexes added ~30MB to the 100,000-bug dataset's database size
  (291MB → 321MB) — noted for completeness, not a concern at this scale.

## 17. Reproduction steps

```bash
# 1. Point the stack at a disposable database (see §2) — do not skip this.

# 2. Generate the full dataset (~2.5 minutes).
BUGFIXER_DISPOSABLE_DATABASE=true docker compose exec backend \
  python manage.py generate_perf_dataset --full --confirm-disposable-database --seed 100

# 3. Run every measurement scenario.
docker compose exec backend python manage.py measure_performance \
  --organization perf-001 --runs 15 --warmup-runs 2 --include-sql \
  --output /tmp/measure.json

# 4. Inspect a specific query plan directly, e.g.:
docker compose exec backend python manage.py shell -c "
from apps.organizations.models import Organization
from apps.bugs.selectors import list_bugs
from apps.accounts.models import User
org = Organization.objects.get(slug='perf-001')
user = User.objects.filter(organizationmembership__organization=org, organizationmembership__role='administrator').first()
print(list_bugs(org, viewer=user, search='chart')[:25].explain(analyze=True, buffers=True))
"

# 5. Clean up when finished.
BUGFIXER_DISPOSABLE_DATABASE=true docker compose exec backend \
  python manage.py generate_perf_dataset --cleanup-existing-perf-data --confirm-disposable-database
```

Every number in this document is reproducible with `--seed 100` (full) or
the command's own default `--seed 42` (small) against a freshly migrated
disposable database.

## 18. Future work

- Cursor (keyset) pagination for `GET /api/bugs/` (and any other endpoint
  that turns out to need deep pages in practice) — §13.
- Investigate `analytics-recent-activity`'s pagination `COUNT(*)` cost with
  the same EXPLAIN-first discipline used in §11 — §16.
- Concurrent-load / multi-worker measurement (this chunk is single-request,
  sequential only).
- A real (not in-process) HTTP-level measurement pass, to capture what
  §16 explicitly excludes.
