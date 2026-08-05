"""Domain-level authorization for the bugs app.

These functions are the single source of truth for "who can do what" —
apps.bugs.views uses them for coarse, pre-object checks (can this role even
hit this endpoint) and apps.bugs.services uses the same functions again for
the fine-grained, object-level checks (is *this* bug editable by *this*
caller right now). Keeping both call sites on the same functions means a
service invoked directly (a future Celery task, a management command, a
test) enforces identical rules to the API, instead of the view being the
only place authorization actually happens.
"""

from apps.bugs.models import BugStatus
from apps.organizations.models import CommunityRole

STAFF_ROLES = frozenset({CommunityRole.ADMINISTRATOR, CommunityRole.DEVELOPER, CommunityRole.QA})
ASSIGNABLE_ROLES = STAFF_ROLES
CREATE_ROLES = STAFF_ROLES | {CommunityRole.REPORTER}

REPORTER_EDITABLE_STATUSES = frozenset({BugStatus.NEW, BugStatus.TRIAGED})
REOPEN_ELIGIBLE_STATUSES = frozenset(
    {
        BugStatus.RESOLVED,
        BugStatus.CLOSED,
        BugStatus.DUPLICATE,
        BugStatus.CANNOT_REPRODUCE,
        BugStatus.WONT_FIX,
    }
)

REPORTER_EDITABLE_FIELDS = frozenset(
    {
        "title",
        "description",
        "steps_to_reproduce",
        "expected_result",
        "actual_result",
        "environment",
        "category",
    }
)
STAFF_EDITABLE_FIELDS = REPORTER_EDITABLE_FIELDS | {"due_date", "priority", "severity"}


class BugPermissionDenied(Exception):
    pass


def is_bug_reporter(bug, user) -> bool:
    return user is not None and bug.reporter_id == user.pk


def _membership_is_bug_reporter(bug, membership) -> bool:
    """Compares against membership.user_id directly rather than loading
    membership.user — avoids a lazy FK fetch on every policy check."""
    return membership is not None and bug.reporter_id == membership.user_id


def can_create_bug(membership) -> bool:
    return membership is not None and membership.role in CREATE_ROLES


def editable_fields_for(bug, membership) -> frozenset[str]:
    """Fields the given membership may currently PATCH on this bug — the
    empty set means "may not edit this bug's content at all right now",
    not "may edit nothing" as a permanent rule (e.g. a reporter's own bug
    becomes uneditable to them once work starts, not forever)."""
    if membership is None:
        return frozenset()
    if membership.role in STAFF_ROLES:
        return STAFF_EDITABLE_FIELDS
    if membership.role == CommunityRole.REPORTER and _membership_is_bug_reporter(bug, membership):
        if bug.status in REPORTER_EDITABLE_STATUSES:
            return REPORTER_EDITABLE_FIELDS
    return frozenset()


def can_change_status(bug, membership, target_status: str) -> bool:
    if membership is None:
        return False
    if membership.role in STAFF_ROLES:
        return True
    if membership.role == CommunityRole.REPORTER:
        return (
            _membership_is_bug_reporter(bug, membership)
            and bug.status in REOPEN_ELIGIBLE_STATUSES
            and target_status == BugStatus.REOPENED
        )
    return False


def can_assign_bug(membership) -> bool:
    return membership is not None and membership.role in ASSIGNABLE_ROLES


def can_archive_bug(membership) -> bool:
    return membership is not None and membership.role == CommunityRole.ADMINISTRATOR


def can_manage_tags(bug, membership) -> bool:
    return bool(editable_fields_for(bug, membership))


def can_manage_relationships(membership) -> bool:
    return membership is not None and membership.role in STAFF_ROLES


def is_eligible_assignee_role(role: str) -> bool:
    return role in ASSIGNABLE_ROLES
