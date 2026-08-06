"""Dashboard aggregation queries.

Every function here is one PostgreSQL aggregate query (or, for trends, two —
one for created, one for resolved-throughput — plus zero-filling the result
in Python, which is response shaping, not aggregation). Nothing here loads
raw Bug rows into Python to sum/group them.

Every query is organization-scoped and excludes archived bugs and bugs
belonging to an archived project by default — the dashboard is an
operational "what needs attention" view, not a historical archive browser.

Date-range boundaries use Django's configured timezone (settings.TIME_ZONE)
via timezone.get_current_timezone(), not a per-organization timezone —
Organization has no timezone field yet. This is a documented Community
limitation (see docs/ACCESS_AND_TESTING.md), not an oversight.
"""

from __future__ import annotations

import datetime

from django.db.models import Avg, Count, F, Q, QuerySet
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.activities.models import ActivityVerb, BugActivity
from apps.bugs.models import Bug, BugPriority, BugSeverity, BugStatus
from apps.bugs.policies import STAFF_ROLES
from apps.bugs.workflow import OPEN_STATUSES, RESOLUTION_STATUSES
from apps.organizations.models import OrganizationMembership
from apps.projects.models import Project

# -- date-range helpers ------------------------------------------------------


def day_bounds(
    date_from: datetime.date, date_to: datetime.date
) -> tuple[datetime.datetime, datetime.datetime]:
    """Half-open [start, end) timezone-aware bounds covering every moment of
    date_from through date_to inclusive, in Django's configured timezone."""
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.datetime.combine(date_from, datetime.time.min), tz)
    end = timezone.make_aware(
        datetime.datetime.combine(date_to + datetime.timedelta(days=1), datetime.time.min), tz
    )
    return start, end


def date_range(date_from: datetime.date, date_to: datetime.date) -> list[datetime.date]:
    """Every calendar date from date_from through date_to inclusive."""
    days = (date_to - date_from).days
    return [date_from + datetime.timedelta(days=i) for i in range(days + 1)]


# -- base queryset -------------------------------------------------------


def _base_bugs(organization, *, project_id: str | None = None) -> QuerySet[Bug]:
    qs = Bug.objects.filter(
        organization=organization, archived_at__isnull=True, project__archived_at__isnull=True
    )
    if project_id:
        qs = qs.filter(project_id=project_id)
    return qs


def _base_resolution_activity(
    organization, *, project_id: str | None = None, start=None, end=None
) -> QuerySet[BugActivity]:
    qs = BugActivity.objects.filter(
        organization=organization,
        verb=ActivityVerb.STATUS_CHANGED,
        to_value__in=RESOLUTION_STATUSES,
        # bug__organization=organization is redundant with organization=
        # above — a BugActivity's bug always belongs to the same
        # organization by construction — but stating it explicitly gives
        # the query planner a directly usable predicate on bugs_bug itself.
        # Without it, confirmed via EXPLAIN ANALYZE against a
        # 100,000-bug/5-organization performance dataset
        # (docs/PERFORMANCE.md): the planner has no organization-scoped
        # way to restrict the bugs_bug side of this join, and — once
        # activities_verb_lookup_idx (added alongside this) made the
        # BugActivity side of the join cheap enough — chose a Hash Join
        # built from a full sequential scan of *every* organization's
        # non-archived bugs (regressing this query from ~20ms to ~43ms).
        # With this filter present, the planner instead restricts
        # bugs_bug to this organization first, via its own existing
        # (organization, archived_at, created_at) index.
        bug__organization=organization,
        bug__archived_at__isnull=True,
        bug__project__archived_at__isnull=True,
    )
    if project_id:
        qs = qs.filter(bug__project_id=project_id)
    if start is not None:
        qs = qs.filter(created_at__gte=start)
    if end is not None:
        qs = qs.filter(created_at__lt=end)
    return qs


# -- summary (point-in-time: open, overdue) -------------------------------


def open_bug_count(organization, *, project_id: str | None = None) -> int:
    return _base_bugs(organization, project_id=project_id).filter(status__in=OPEN_STATUSES).count()


def overdue_bug_count(organization, *, project_id: str | None = None) -> int:
    today = timezone.localdate()
    return (
        _base_bugs(organization, project_id=project_id)
        .filter(status__in=OPEN_STATUSES, due_date__lt=today)
        .count()
    )


# -- summary (date-ranged: new, resolved) ---------------------------------


def new_bug_count(
    organization, *, project_id: str | None, date_from: datetime.date, date_to: datetime.date
) -> int:
    start, end = day_bounds(date_from, date_to)
    return (
        _base_bugs(organization, project_id=project_id)
        .filter(created_at__gte=start, created_at__lt=end)
        .count()
    )


def resolved_bug_count(
    organization, *, project_id: str | None, date_from: datetime.date, date_to: datetime.date
) -> int:
    """Throughput count: how many resolution-transition events happened in
    range, via immutable BugActivity — stays correct even for a bug later
    reopened. See apps.analytics docs for why this differs deliberately
    from resolution_time_by_priority's population."""
    start, end = day_bounds(date_from, date_to)
    return _base_resolution_activity(
        organization, project_id=project_id, start=start, end=end
    ).count()


# -- trends -----------------------------------------------------------------


def trends(
    organization, *, project_id: str | None, date_from: datetime.date, date_to: datetime.date
) -> list[dict]:
    start, end = day_bounds(date_from, date_to)
    tz = timezone.get_current_timezone()

    created_rows = (
        _base_bugs(organization, project_id=project_id)
        .filter(created_at__gte=start, created_at__lt=end)
        .annotate(day=TruncDate("created_at", tzinfo=tz))
        .values("day")
        .annotate(count=Count("id"))
    )
    created_by_day = {row["day"]: row["count"] for row in created_rows}

    resolved_rows = (
        _base_resolution_activity(organization, project_id=project_id, start=start, end=end)
        .annotate(day=TruncDate("created_at", tzinfo=tz))
        .values("day")
        .annotate(count=Count("id"))
    )
    resolved_by_day = {row["day"]: row["count"] for row in resolved_rows}

    # Zero-filling here is response shaping, not authoritative aggregation —
    # the counts themselves came straight from the two GROUP BY queries above.
    return [
        {"date": d, "created": created_by_day.get(d, 0), "resolved": resolved_by_day.get(d, 0)}
        for d in date_range(date_from, date_to)
    ]


# -- resolution time by priority -------------------------------------------


def resolution_time_by_priority(
    organization, *, project_id: str | None, date_from: datetime.date, date_to: datetime.date
) -> dict[str, datetime.timedelta | None]:
    """Average (resolved_at - created_at) for bugs whose *current* status is
    still a resolution status and whose resolved_at falls in range. A bug
    that was resolved and later reopened has resolved_at=None right now and
    is excluded — see module docstring / docs/ACCESS_AND_TESTING.md for why
    this intentionally differs from resolved_bug_count/trends."""
    start, end = day_bounds(date_from, date_to)
    rows = (
        _base_bugs(organization, project_id=project_id)
        .filter(status__in=RESOLUTION_STATUSES, resolved_at__gte=start, resolved_at__lt=end)
        .values("priority")
        .annotate(avg_duration=Avg(F("resolved_at") - F("created_at")))
    )
    by_priority = {row["priority"]: row["avg_duration"] for row in rows}
    return {p: by_priority.get(p) for p in BugPriority.values}


# -- distributions (point-in-time: status, severity) -----------------------


def status_distribution(organization, *, project_id: str | None = None) -> dict[str, int]:
    rows = (
        _base_bugs(organization, project_id=project_id).values("status").annotate(count=Count("id"))
    )
    counts = {row["status"]: row["count"] for row in rows}
    return {s: counts.get(s, 0) for s in BugStatus.values}


def severity_distribution(organization, *, project_id: str | None = None) -> dict[str, int]:
    rows = (
        _base_bugs(organization, project_id=project_id)
        .values("severity")
        .annotate(count=Count("id"))
    )
    counts = {row["severity"]: row["count"] for row in rows}
    return {s: counts.get(s, 0) for s in BugSeverity.values}


# -- workload (point-in-time, current non-closed only) ----------------------


def _display_name(first_name: str, last_name: str, email: str) -> str:
    full = f"{first_name} {last_name}".strip()
    return full or email


def workload(organization, *, project_id: str | None = None) -> dict:
    """Groups currently-open bugs by current assignee.

    A single membership lookup (one IN query over the distinct assignee ids
    already returned by the group-by) classifies each assignee — never one
    query per developer. Bugs assigned to a member whose *current* role is
    no longer in STAFF_ROLES (demoted, or — defensively — a membership that
    no longer exists at all despite clear_bug_assignments normally
    preventing that) land under "needs_reassignment" rather than silently
    disappearing or being folded into ordinary workload.
    """
    rows = (
        _base_bugs(organization, project_id=project_id)
        .filter(status__in=OPEN_STATUSES)
        .values("assignee_id", "assignee__first_name", "assignee__last_name", "assignee__email")
        .annotate(count=Count("id"))
        .order_by()
    )

    assignee_ids = [row["assignee_id"] for row in rows if row["assignee_id"] is not None]
    roles_by_user = dict(
        OrganizationMembership.objects.filter(
            organization=organization, user_id__in=assignee_ids
        ).values_list("user_id", "role")
    )

    unassigned_count = 0
    eligible: list[dict] = []
    needs_reassignment: list[dict] = []

    for row in rows:
        assignee_id = row["assignee_id"]
        if assignee_id is None:
            unassigned_count = row["count"]
            continue
        entry = {
            "user_id": assignee_id,
            "name": _display_name(
                row["assignee__first_name"] or "",
                row["assignee__last_name"] or "",
                row["assignee__email"],
            ),
            "role": roles_by_user.get(assignee_id),
            "count": row["count"],
        }
        if entry["role"] in STAFF_ROLES:
            eligible.append(entry)
        else:
            needs_reassignment.append(entry)

    eligible.sort(key=lambda e: e["count"], reverse=True)
    needs_reassignment.sort(key=lambda e: e["count"], reverse=True)

    return {
        "eligible": eligible,
        "unassigned": unassigned_count,
        "needs_reassignment": needs_reassignment,
    }


# -- recent activity (point-in-time, bounded/paginated by the view) --------


def recent_activity(organization, *, project_id: str | None = None) -> QuerySet[BugActivity]:
    qs = BugActivity.objects.filter(
        organization=organization,
        bug__archived_at__isnull=True,
        bug__project__archived_at__isnull=True,
    ).select_related("bug", "bug__project", "actor")
    if project_id:
        qs = qs.filter(bug__project_id=project_id)
    return qs.order_by("-created_at", "-id")


# -- active projects ---------------------------------------------------------


def active_projects(organization) -> QuerySet[Project]:
    """Non-archived projects with total/open bug totals — two conditional
    Count() aggregates over the single `bugs` join, which Postgres computes
    as COUNT(CASE WHEN ... THEN bug.id END); no fan-out, so no distinct=True
    is needed (verified via EXPLAIN during Phase 5 implementation)."""
    return (
        Project.objects.filter(organization=organization, archived_at__isnull=True)
        .annotate(
            total_bugs=Count("bugs", filter=Q(bugs__archived_at__isnull=True)),
            open_bugs=Count(
                "bugs", filter=Q(bugs__archived_at__isnull=True, bugs__status__in=OPEN_STATUSES)
            ),
        )
        .order_by("name")
    )
