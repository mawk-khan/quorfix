"""Shared backdating helper for development-only demo/fixture data.

Used by seed_demo (apps.core.management.commands.seed_demo) and the
Playwright analytics fixture (apps.core.management.commands.
seed_e2e_analytics_fixture) — both need the same trick for the same reason:
giving a bug a historical created_at/resolved_at/closed_at so the analytics
dashboard has more than a single instant of data to chart, without
disturbing the real service-layer invariants (numbering, activity
immutability as a *convention*) any more than strictly necessary.

Not imported by anything outside management commands. Both call sites are
already gated by their own production guard before this ever runs.
"""

from __future__ import annotations

import datetime

from django.utils import timezone

from apps.activities.models import ActivityVerb, BugActivity
from apps.bugs.models import Bug, BugStatus
from apps.bugs.workflow import RESOLUTION_STATUSES


def backdate_bug_history(
    bug: Bug,
    *,
    reference_now: datetime.datetime,
    created_days_ago: int | None = None,
    resolution_days_ago: list[int] | None = None,
    closed_days_ago: int | None = None,
) -> None:
    """Rewrites this bug's timestamps to sit in the past, deterministically,
    relative to a single captured `reference_now` (not repeated
    timezone.now() calls, so every bug in one command run is backdated
    consistently even if the run happens to straddle a clock second).

    Uses queryset.update() throughout — the only way to give an
    auto_now_add field (created_at) a past value, and the same deliberate
    exception to "activity is immutable" that both call sites already
    document at their own production guard.

    `resolution_days_ago` is ordered oldest-first, one entry per
    resolution-transition activity the bug's transition walk actually
    produced (most bugs have one; a bug reopened and resolved again has
    two). Only creation and resolution/closure are backdated — intermediate
    workflow-step activities (triaged/assigned/in_progress/reopened) are
    left at whenever the command actually ran, which is a cosmetic
    simplification (a bug's full history looks compressed) rather than a
    correctness issue for anything the dashboard computes.
    """
    updates: dict = {}

    if created_days_ago is not None:
        created_at = reference_now - datetime.timedelta(days=created_days_ago)
        updates["created_at"] = created_at
        BugActivity.objects.filter(bug=bug, verb=ActivityVerb.CREATED).update(created_at=created_at)

    if resolution_days_ago:
        resolution_activities = list(
            BugActivity.objects.filter(
                bug=bug, verb=ActivityVerb.STATUS_CHANGED, to_value__in=list(RESOLUTION_STATUSES)
            ).order_by("created_at")
        )
        for activity, days_ago in zip(resolution_activities, resolution_days_ago, strict=True):
            BugActivity.objects.filter(pk=activity.pk).update(
                created_at=reference_now - datetime.timedelta(days=days_ago)
            )
        if bug.status in RESOLUTION_STATUSES:
            updates["resolved_at"] = reference_now - datetime.timedelta(
                days=resolution_days_ago[-1]
            )

    if closed_days_ago is not None:
        closed_at = reference_now - datetime.timedelta(days=closed_days_ago)
        updates["closed_at"] = closed_at
        BugActivity.objects.filter(
            bug=bug, verb=ActivityVerb.STATUS_CHANGED, to_value=BugStatus.CLOSED
        ).update(created_at=closed_at)
        if "resolved_at" not in updates and resolution_days_ago:
            updates["resolved_at"] = reference_now - datetime.timedelta(
                days=resolution_days_ago[-1]
            )

    if updates:
        Bug.objects.filter(pk=bug.pk).update(**updates)


def due_date_days_ago(days_ago: int | None) -> datetime.date | None:
    if days_ago is None:
        return None
    return timezone.localdate() - datetime.timedelta(days=days_ago)
