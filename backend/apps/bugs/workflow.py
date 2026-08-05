"""Community's default bug workflow, and the extension point Professional
custom workflows will hook into later.

Community code here never asks "is custom_workflows licensed" or imports
anything from a Professional module — it only ever asks the shared
workflow_registry "is a provider registered, and does it apply to this
project". If nothing is registered (the only possible state while
Professional is absent, and the state every Community-only test exercises),
get_transition_matrix falls back to COMMUNITY_TRANSITIONS unconditionally.
A future Professional module registers a provider from its own
AppConfig.ready() and enforces the custom_workflows capability *inside its
own provider*, not here.
"""

from __future__ import annotations

from typing import Protocol

from apps.bugs.models import BugStatus
from apps.core.registries import workflow_registry

WORKFLOW_PROVIDER_KEY = "bug_workflow_provider"

RESOLUTION_STATUSES = frozenset(
    {BugStatus.RESOLVED, BugStatus.DUPLICATE, BugStatus.CANNOT_REPRODUCE, BugStatus.WONT_FIX}
)

# Entering ASSIGNED or IN_PROGRESS from anywhere requires the bug to end up
# with a non-null assignee (either already set, or supplied atomically in
# the same transition request) — covers both "new -> assigned" and
# "triaged -> in_progress" from the Phase 3 spec, and keeps the invariant
# general instead of hardcoding those two edges specifically.
ASSIGNEE_REQUIRED_STATUSES = frozenset({BugStatus.ASSIGNED, BugStatus.IN_PROGRESS})

COMMUNITY_TRANSITIONS: dict[str, frozenset[str]] = {
    BugStatus.NEW: frozenset(
        {
            BugStatus.TRIAGED,
            BugStatus.ASSIGNED,
            BugStatus.BLOCKED,
            BugStatus.DUPLICATE,
            BugStatus.CANNOT_REPRODUCE,
            BugStatus.WONT_FIX,
        }
    ),
    BugStatus.TRIAGED: frozenset(
        {
            BugStatus.ASSIGNED,
            BugStatus.IN_PROGRESS,
            BugStatus.BLOCKED,
            BugStatus.DEFERRED,
            BugStatus.DUPLICATE,
            BugStatus.CANNOT_REPRODUCE,
            BugStatus.WONT_FIX,
        }
    ),
    BugStatus.ASSIGNED: frozenset(
        {BugStatus.IN_PROGRESS, BugStatus.TRIAGED, BugStatus.BLOCKED, BugStatus.DEFERRED}
    ),
    BugStatus.IN_PROGRESS: frozenset(
        {
            BugStatus.READY_FOR_QA,
            BugStatus.RESOLVED,
            BugStatus.BLOCKED,
            BugStatus.DEFERRED,
            BugStatus.ASSIGNED,
        }
    ),
    BugStatus.READY_FOR_QA: frozenset(
        {BugStatus.RESOLVED, BugStatus.IN_PROGRESS, BugStatus.BLOCKED}
    ),
    # Deliberately narrow: Community does not remember what state a bug was
    # blocked from and auto-return to it. Whoever unblocks it chooses
    # explicitly between re-triaging or resuming active work.
    BugStatus.BLOCKED: frozenset({BugStatus.TRIAGED, BugStatus.IN_PROGRESS}),
    BugStatus.DEFERRED: frozenset({BugStatus.TRIAGED, BugStatus.ASSIGNED, BugStatus.IN_PROGRESS}),
    BugStatus.RESOLVED: frozenset({BugStatus.CLOSED, BugStatus.REOPENED}),
    BugStatus.CLOSED: frozenset({BugStatus.REOPENED}),
    BugStatus.REOPENED: frozenset(
        {BugStatus.TRIAGED, BugStatus.ASSIGNED, BugStatus.IN_PROGRESS, BugStatus.BLOCKED}
    ),
    BugStatus.DUPLICATE: frozenset({BugStatus.REOPENED}),
    BugStatus.CANNOT_REPRODUCE: frozenset({BugStatus.REOPENED}),
    BugStatus.WONT_FIX: frozenset({BugStatus.REOPENED}),
}


class WorkflowProvider(Protocol):
    def applies_to(self, project) -> bool: ...

    def transitions_for(self, project) -> dict[str, frozenset[str]]: ...


def get_transition_matrix(project) -> dict[str, frozenset[str]]:
    provider: WorkflowProvider | None = workflow_registry.get(WORKFLOW_PROVIDER_KEY)
    if provider is not None and provider.applies_to(project):
        return provider.transitions_for(project)
    return COMMUNITY_TRANSITIONS


def is_valid_transition(project, from_status: str, to_status: str) -> bool:
    matrix = get_transition_matrix(project)
    return to_status in matrix.get(from_status, frozenset())


def apply_timestamp_side_effects(bug, to_status: str) -> None:
    """Purely a function of the *target* status, so it stays correct for
    any transition path — including ones a future Professional workflow
    provider adds — without needing to special-case "coming from resolved"
    anywhere."""
    from django.utils import timezone

    if to_status in RESOLUTION_STATUSES:
        bug.resolved_at = timezone.now()
    elif to_status == BugStatus.CLOSED:
        bug.closed_at = timezone.now()
    elif to_status == BugStatus.REOPENED:
        bug.resolved_at = None
        bug.closed_at = None
