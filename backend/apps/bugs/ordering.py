"""Shared bug-domain ordering definitions.

Priority and severity are stored as free-standing TextChoices, so their
natural declaration order is not their business ordering — "urgent" must
sort above "low", "blocker" above "trivial", regardless of enum declaration
order. This is the single source of truth for that ordering: apps.bugs
uses it to sort bug list results, apps.analytics uses it to order
distribution/resolution-time chart output. Neither app should redefine it,
and apps.analytics must not reach into apps.bugs.selectors (a list/query
module, not a shared-constants module) to get it.
"""

from __future__ import annotations

from django.db.models import Case, IntegerField, Value, When

from apps.bugs.models import BugPriority, BugSeverity

PRIORITY_RANK = {
    BugPriority.LOW: 0,
    BugPriority.MEDIUM: 1,
    BugPriority.HIGH: 2,
    BugPriority.URGENT: 3,
}

SEVERITY_RANK = {
    BugSeverity.TRIVIAL: 0,
    BugSeverity.MINOR: 1,
    BugSeverity.MAJOR: 2,
    BugSeverity.CRITICAL: 3,
    BugSeverity.BLOCKER: 4,
}


def rank_case(field: str, rank_map: dict) -> Case:
    return Case(
        *[When(**{field: value}, then=Value(rank)) for value, rank in rank_map.items()],
        output_field=IntegerField(),
    )
