"""Measures real API view performance against a generated dataset.

Authenticates as a real member of a chosen organization (via Django's test
client session login — no password is ever printed or logged) and invokes
real DRF views through rest_framework.test.APIClient, exactly the same view
code a browser request would hit, end to end (URL routing, permission
classes, selectors, serializers) — network transport itself is the only
thing not represented, which is exactly the point: this isolates
application/database performance from local network variability.

Not gated behind QUORFIX_DISPOSABLE_DATABASE — this command only ever reads
data and issues requests against the already-running application; it never
writes application data or deletes anything. It does require at least one
organization matching the perf-owned naming convention
(apps.core.management.commands.generate_perf_dataset.PERF_SLUG_PREFIX) to
exist, since there is nothing meaningful to authenticate as or measure
against otherwise.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.attachments.models import Attachment
from apps.bugs.models import Bug
from apps.comments.models import Comment
from apps.core.management.commands.generate_perf_dataset import PERF_SLUG_PREFIX
from apps.organizations.models import Organization, OrganizationMembership


@dataclass
class RunResult:
    status_code: int
    duration_seconds: float
    response_bytes: int
    query_count: int
    sql_time_seconds: float
    slow_queries: list = field(default_factory=list)


@dataclass
class ScenarioResult:
    name: str
    description: str
    runs: list  # list[RunResult]
    error: str | None = None

    def to_dict(self) -> dict:
        if self.error:
            return {"name": self.name, "description": self.description, "error": self.error}
        durations = [r.duration_seconds for r in self.runs]
        sizes = [r.response_bytes for r in self.runs]
        query_counts = [r.query_count for r in self.runs]
        sql_times = [r.sql_time_seconds for r in self.runs]
        return {
            "name": self.name,
            "description": self.description,
            "sample_count": len(self.runs),
            "status_codes": sorted({r.status_code for r in self.runs}),
            "duration_ms": {
                "median": round(statistics.median(durations) * 1000, 2),
                "min": round(min(durations) * 1000, 2),
                "max": round(max(durations) * 1000, 2),
                "p95": round(_percentile(durations, 95) * 1000, 2)
                if len(durations) >= 20
                else None,
            },
            "response_bytes": {"median": int(statistics.median(sizes)), "max": max(sizes)},
            "query_count": {"median": statistics.median(query_counts), "max": max(query_counts)},
            "sql_time_ms": {
                "median": round(statistics.median(sql_times) * 1000, 2),
                "max": round(max(sql_times) * 1000, 2),
            },
            "slowest_queries": self.runs[-1].slow_queries,
        }


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


class Command(BaseCommand):
    help = (
        "Runs a fixed set of real, authenticated API requests against a "
        "generated performance dataset and reports timing/query-count "
        "statistics. Read-only — writes nothing, deletes nothing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--organization",
            default=None,
            help="Perf organization slug to measure against (default: the first perf-owned "
            "organization found).",
        )
        parser.add_argument("--runs", type=int, default=10)
        parser.add_argument("--warmup-runs", type=int, default=2)
        parser.add_argument("--output", default=None, help="Path to write JSON results.")
        parser.add_argument(
            "--include-sql",
            action="store_true",
            help="Include the 5 slowest captured SQL statements (from the last run of each "
            "scenario) in the report. Never includes bind parameter values beyond what "
            "Django's own query log already captures.",
        )
        parser.add_argument(
            "--scenario",
            default=None,
            help="Run only the named scenario instead of every scenario. See --help output "
            "or docs/PERFORMANCE.md for the full list of names.",
        )

    def handle(self, *args, **options):
        # APIClient's default test host ("testserver") isn't in ALLOWED_HOSTS
        # outside a real django.test.TestCase run (which patches this
        # automatically) — invoked here via plain `manage.py`, nothing else
        # does that for us. Appending it for the life of this process only;
        # never written to settings files or the environment.
        if "testserver" not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS.append("testserver")

        organization = self._resolve_organization(options["organization"])
        member = self._resolve_member(organization)

        self.stdout.write(
            f"Measuring against organization {organization.slug!r} "
            f"as {member.role} member (runs={options['runs']}, warmup={options['warmup_runs']})."
        )

        client = APIClient()
        client.force_login(member.user)

        context = ScenarioContext(
            client=client,
            organization=organization,
            member=member,
            runs=options["runs"],
            warmup_runs=options["warmup_runs"],
            include_sql=options["include_sql"],
        )

        scenarios = _build_scenarios(context)
        if options["scenario"]:
            scenarios = [s for s in scenarios if s.name == options["scenario"]]
            if not scenarios:
                raise CommandError(
                    f"Unknown scenario {options['scenario']!r}. Run without --scenario to see "
                    "every available name in the report, or check docs/PERFORMANCE.md."
                )

        results = []
        for scenario in scenarios:
            self.stdout.write(f"  {scenario.name} ... ", ending="")
            result = _run_scenario(context, scenario)
            results.append(result)
            if result.error:
                self.stdout.write(self.style.ERROR(f"ERROR: {result.error}"))
            else:
                d = result.to_dict()
                self.stdout.write(
                    f"median={d['duration_ms']['median']}ms "
                    f"p95={d['duration_ms']['p95']}ms "
                    f"queries={d['query_count']['median']} "
                    f"status={d['status_codes']}"
                )

        report = {
            "organization": organization.slug,
            "runs": options["runs"],
            "warmup_runs": options["warmup_runs"],
            "scenarios": [r.to_dict() for r in results],
        }

        if options["output"]:
            with open(options["output"], "w") as fh:
                json.dump(report, fh, indent=2, default=str)
            self.stdout.write(self.style.SUCCESS(f"Wrote JSON report to {options['output']}."))

    # -- setup ------------------------------------------------------------

    def _resolve_organization(self, slug: str | None) -> Organization:
        qs = Organization.objects.filter(slug__startswith=PERF_SLUG_PREFIX)
        if slug:
            org = qs.filter(slug=slug).first()
            if org is None:
                raise CommandError(
                    f"No perf-owned organization with slug {slug!r} found. Run "
                    "generate_perf_dataset first."
                )
            return org
        org = qs.order_by("slug").first()
        if org is None:
            raise CommandError(
                "No perf-owned organization found. Run generate_perf_dataset first "
                "(see docs/PERFORMANCE.md)."
            )
        return org

    def _resolve_member(self, organization: Organization) -> OrganizationMembership:
        member = (
            OrganizationMembership.objects.select_related("user")
            .filter(organization=organization, role="administrator")
            .first()
        )
        if member is None:
            raise CommandError(f"Organization {organization.slug!r} has no administrator member.")
        return member


@dataclass
class ScenarioContext:
    client: APIClient
    organization: Organization
    member: OrganizationMembership
    runs: int
    warmup_runs: int
    include_sql: bool


@dataclass
class Scenario:
    name: str
    description: str
    request: object  # Callable[[], tuple[str, dict | None]] -> (path, query params)
    method: str = "get"
    cache_mode: str | None = None  # None | "cold" | "warm" | "redis-unavailable"


def _run_scenario(context: ScenarioContext, scenario: Scenario) -> ScenarioResult:
    try:
        path, query = scenario.request()
    except _NoFixtureData as exc:
        return ScenarioResult(scenario.name, scenario.description, [], error=str(exc))

    redis_override = None
    if scenario.cache_mode == "warm":
        cache.clear()
        context.client.get(path, query, format="json")  # prime the cache, not measured
    elif scenario.cache_mode == "redis-unavailable":
        from django.test import override_settings

        redis_override = override_settings(
            CACHES={
                "default": {
                    "BACKEND": "django.core.cache.backends.redis.RedisCache",
                    # Port 1 is a reserved, never-listening port — guarantees a
                    # real connection failure rather than a flaky race against
                    # an actually-running service on some other port.
                    "LOCATION": "redis://127.0.0.1:1/0",
                }
            }
        )
        redis_override.enable()

    try:
        # "cold" specifically means every single measured request is a
        # genuine cache miss — a warmup pass here would prime exactly the
        # cache the scenario exists to bypass, and clearing once before the
        # whole run loop (rather than before each iteration) would leave
        # all but the first of --runs iterations warm regardless. Neither
        # concern applies to any other cache_mode.
        if scenario.cache_mode != "cold":
            for _ in range(context.warmup_runs):
                context.client.get(path, query, format="json")

        runs = []
        for i in range(context.runs):
            if scenario.cache_mode == "cold":
                cache.clear()
            with CaptureQueriesContext(connection) as captured:
                started = time.perf_counter()
                response = context.client.get(path, query, format="json")
                duration = time.perf_counter() - started

            sql_time = sum(float(q["time"]) for q in captured.captured_queries)
            slow = []
            if context.include_sql and i == context.runs - 1:
                ordered = sorted(captured.captured_queries, key=lambda q: -float(q["time"]))
                slow = [
                    {"time_ms": round(float(q["time"]) * 1000, 2), "sql": q["sql"][:300]}
                    for q in ordered[:5]
                ]

            runs.append(
                RunResult(
                    status_code=response.status_code,
                    duration_seconds=duration,
                    response_bytes=len(response.content),
                    query_count=len(captured.captured_queries),
                    sql_time_seconds=sql_time,
                    slow_queries=slow,
                )
            )
    finally:
        if redis_override is not None:
            redis_override.disable()

    return ScenarioResult(scenario.name, scenario.description, runs)


class _NoFixtureData(Exception):
    """Raised by a scenario's request() when the organization has no data
    shaped the way that scenario needs (e.g. no bug with any comments) —
    reported as a per-scenario error in the JSON output rather than
    crashing the whole run, since not every profile/seed combination is
    guaranteed to produce every shape (an org generated with
    --comments-per-bug 0, for instance)."""


def _build_scenarios(context: ScenarioContext) -> list[Scenario]:
    import datetime

    from apps.projects.models import Project

    org = context.organization
    projects = list(Project.objects.filter(organization=org).order_by("key")[:2])
    first_project = projects[0] if projects else None

    today = datetime.date.today()
    date_range_params = {
        "date_from": str(today - datetime.timedelta(days=30)),
        "date_to": str(today),
    }

    any_bug = Bug.objects.filter(organization=org).order_by("id").first()
    # A real assignee_id with actual assigned bugs (not just any non-viewer
    # member) — so the filter scenario measures a realistic non-empty
    # result set rather than an arbitrary, possibly-empty one.
    real_assignee_id = (
        Bug.objects.filter(organization=org, assignee__isnull=False)
        .values_list("assignee_id", flat=True)
        .first()
    )

    def _bug_with_most_comments():
        from django.db.models import Count

        row = (
            Comment.objects.filter(organization=org)
            .values("bug_id")
            .annotate(n=Count("id"))
            .order_by("-n")
            .first()
        )
        if not row:
            raise _NoFixtureData("no bug in this organization has any comments")
        return row["bug_id"]

    def _bug_with_attachments():
        row = Attachment.objects.filter(organization=org).values_list("bug_id", flat=True).first()
        if not row:
            raise _NoFixtureData("no bug in this organization has any attachment metadata")
        return row

    def _bug_with_most_activity():
        from django.db.models import Count

        from apps.activities.models import BugActivity

        row = (
            BugActivity.objects.filter(organization=org)
            .values("bug_id")
            .annotate(n=Count("id"))
            .order_by("-n")
            .first()
        )
        if not row:
            raise _NoFixtureData("no bug in this organization has any activity")
        return row["bug_id"]

    def require_bug():
        if any_bug is None:
            raise _NoFixtureData("this organization has no bugs")
        return any_bug

    scenarios: list[Scenario] = [
        Scenario(
            "bugs-first-page",
            "GET /api/bugs/ (first page, default ordering)",
            lambda: (reverse("bug-list"), {}),
        ),
        Scenario(
            "bugs-project-filter",
            "GET /api/bugs/?project=<id>",
            lambda: (reverse("bug-list"), {"project": str(first_project.id)})
            if first_project
            else (_ for _ in ()).throw(_NoFixtureData("no projects in this organization")),
        ),
        Scenario(
            "bugs-status-filter",
            "GET /api/bugs/?status=open",
            lambda: (reverse("bug-list"), {"status": "new,triaged,assigned,in_progress"}),
        ),
        Scenario(
            "bugs-assignee-filter",
            "GET /api/bugs/?assignee=<id>",
            lambda: (reverse("bug-list"), {"assignee": str(real_assignee_id)})
            if real_assignee_id
            else (_ for _ in ()).throw(_NoFixtureData("no assigned bugs in this organization")),
        ),
        Scenario(
            "bugs-search",
            "GET /api/bugs/?search=<term> (icontains title/key match)",
            lambda: (reverse("bug-list"), {"search": "chart"}),
        ),
        Scenario(
            "bugs-max-page-size",
            "GET /api/bugs/?page_size=100 (max allowed)",
            lambda: (reverse("bug-list"), {"page_size": 100}),
        ),
        Scenario(
            "bugs-deep-page",
            "GET /api/bugs/?page=500 (large OFFSET)",
            lambda: (reverse("bug-list"), {"page": 500}),
        ),
        Scenario(
            "bug-detail",
            "GET /api/bugs/<id>/ (includes tags/relationships/policy fields)",
            lambda: (reverse("bug-detail", args=[require_bug().id]), {}),
        ),
        Scenario(
            "bug-activity",
            "GET /api/bugs/<id>/activity/",
            lambda: (reverse("bug-activity", args=[_bug_with_most_activity()]), {}),
        ),
        Scenario(
            "bug-comments",
            "GET /api/bugs/<id>/comments/ (bug with the most comments)",
            lambda: (
                reverse("comment-list-create", kwargs={"bug_id": _bug_with_most_comments()}),
                {},
            ),
        ),
        Scenario(
            "bug-attachments",
            "GET /api/bugs/<id>/attachments/",
            lambda: (
                reverse("attachment-list-create", kwargs={"bug_id": _bug_with_attachments()}),
                {},
            ),
        ),
        Scenario(
            "notifications-first-page",
            "GET /api/notifications/",
            lambda: (reverse("notification-list"), {}),
        ),
        Scenario(
            "notifications-unread-only",
            "GET /api/notifications/?read=false",
            lambda: (reverse("notification-list"), {"read": "false"}),
        ),
        Scenario(
            "notifications-unread-count",
            "GET /api/notifications/unread-count/",
            lambda: (reverse("notification-unread-count"), {}),
        ),
        Scenario("projects-list", "GET /api/projects/", lambda: (reverse("project-list"), {})),
        Scenario(
            "project-detail",
            "GET /api/projects/<id>/",
            lambda: (reverse("project-detail", args=[first_project.id]), {})
            if first_project
            else (_ for _ in ()).throw(_NoFixtureData("no projects in this organization")),
        ),
        Scenario("members-list", "GET /api/members/", lambda: (reverse("membership-list"), {})),
        Scenario(
            "analytics-summary-cold",
            "GET /api/analytics/summary/ (cache cleared first)",
            lambda: (reverse("analytics-summary"), dict(date_range_params)),
            cache_mode="cold",
        ),
        Scenario(
            "analytics-summary-warm",
            "GET /api/analytics/summary/ (primed once first)",
            lambda: (reverse("analytics-summary"), dict(date_range_params)),
            cache_mode="warm",
        ),
        Scenario(
            "analytics-summary-redis-unavailable",
            "GET /api/analytics/summary/ (Redis unreachable)",
            lambda: (reverse("analytics-summary"), dict(date_range_params)),
            cache_mode="redis-unavailable",
        ),
        Scenario(
            "analytics-trends",
            "GET /api/analytics/trends/ (default 30-day range)",
            lambda: (reverse("analytics-trends"), dict(date_range_params)),
            cache_mode="cold",
        ),
        Scenario(
            "analytics-resolution-time",
            "GET /api/analytics/resolution-time/",
            lambda: (reverse("analytics-resolution-time"), dict(date_range_params)),
            cache_mode="cold",
        ),
        Scenario(
            "analytics-distributions",
            "GET /api/analytics/distributions/",
            lambda: (reverse("analytics-distributions"), {}),
            cache_mode="cold",
        ),
        Scenario(
            "analytics-workload",
            "GET /api/analytics/workload/",
            lambda: (reverse("analytics-workload"), {}),
            cache_mode="cold",
        ),
        Scenario(
            "analytics-active-projects",
            "GET /api/analytics/active-projects/",
            lambda: (reverse("analytics-active-projects"), {}),
            cache_mode="cold",
        ),
        Scenario(
            "analytics-recent-activity",
            "GET /api/analytics/recent-activity/ (never cached)",
            lambda: (reverse("analytics-recent-activity"), {}),
        ),
    ]
    return scenarios
