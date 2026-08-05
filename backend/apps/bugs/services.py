from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.bugs import policies, selectors, workflow
from apps.bugs.models import (
    Bug,
    BugPriority,
    BugRelationship,
    BugSeverity,
    BugStatus,
    RelationshipType,
    Tag,
)
from apps.bugs.policies import BugPermissionDenied
from apps.projects.models import Project

User = get_user_model()

MAX_TAG_NAME_LENGTH = 50
MAX_DUPLICATE_CHAIN_DEPTH = 25

UNSET = object()


class BugServiceError(Exception):
    """Common base for every domain exception this module raises, so the
    view layer can dispatch on one type instead of an ever-growing except
    tuple. Not raised directly."""


class ProjectArchivedForBugCreation(BugServiceError):
    pass


class BugArchived(BugServiceError):
    pass


class ProjectArchivedForBugMutation(BugServiceError):
    pass


class BugAlreadyArchived(BugServiceError):
    pass


class BugNotArchived(BugServiceError):
    pass


class BugVersionConflict(BugServiceError):
    def __init__(self, bug: Bug):
        self.bug = bug


class IneligibleAssignee(BugServiceError):
    pass


class AssigneeRequiredForTransition(BugServiceError):
    pass


class InvalidTagName(BugServiceError):
    pass


class InvalidWorkflowTransition(BugServiceError):
    pass


class DuplicateTargetRequired(BugServiceError):
    pass


class DuplicateTargetArchived(BugServiceError):
    pass


class DuplicateCycleDetected(BugServiceError):
    pass


class DuplicateChainUnverifiable(BugServiceError):
    pass


class InvalidRelationshipType(BugServiceError):
    pass


class DuplicateBugRelationship(BugServiceError):
    pass


class SelfRelationshipNotAllowed(BugServiceError):
    pass


class RelatedBugNotFound(BugServiceError):
    pass


class RelationshipNotFound(BugServiceError):
    pass


# -- internal helpers --------------------------------------------------


def _lock_bug(bug: Bug) -> Bug:
    # of=("self",) restricts the row lock to bugs_bug itself — Postgres
    # refuses FOR UPDATE across a LEFT OUTER JOIN on its nullable side
    # (assignee can be null), so locking the joined tables too would raise
    # FeatureNotSupported. We only ever need the Bug row locked; project/
    # reporter/assignee are read-only context for this transaction.
    return (
        Bug.objects.select_for_update(of=("self",))
        .select_related("project", "reporter", "assignee")
        .get(pk=bug.pk)
    )


def _check_version(bug: Bug, expected_version: int) -> None:
    if bug.version != expected_version:
        raise BugVersionConflict(bug)


def _check_mutable(bug: Bug) -> None:
    """Every shared-state mutation must hold both invariants: the bug
    itself isn't archived, and the project it belongs to isn't archived
    either — a project archived after its bugs were created must freeze
    them too, not just block new bugs."""
    if bug.archived_at is not None:
        raise BugArchived()
    if bug.project.archived_at is not None:
        raise ProjectArchivedForBugMutation()


def _record(
    bug: Bug,
    actor,
    verb: str,
    *,
    from_value: str = "",
    to_value: str = "",
    metadata: dict | None = None,
):
    from apps.activities.services import record_bug_activity

    return record_bug_activity(
        bug=bug, actor=actor, verb=verb, from_value=from_value, to_value=to_value, metadata=metadata
    )


def _resolve_assignee(organization, assignee_id):
    if assignee_id is None:
        return None
    if not selectors.is_eligible_assignee(organization, assignee_id):
        raise IneligibleAssignee()
    return User.objects.get(pk=assignee_id)


def normalize_tag_name(raw: str) -> str:
    return raw.strip()


# -- create --------------------------------------------------------------


@transaction.atomic
def create_bug(
    *,
    organization,
    project: Project,
    reporter,
    membership,
    title: str,
    description: str = "",
    steps_to_reproduce: str = "",
    expected_result: str = "",
    actual_result: str = "",
    environment: str = "",
    category: str = "",
    priority: str = BugPriority.MEDIUM,
    severity: str = BugSeverity.MAJOR,
    due_date=None,
) -> Bug:
    """Locks the Project row, assigns the next sequential number, and
    increments the counter, all inside this one transaction — so a rolled
    back creation (e.g. a later constraint failure) rolls the counter back
    with it, and two concurrent creates against the same project can never
    observe the same number (the second waits for the lock, then sees the
    first's already-incremented counter)."""
    from apps.activities.models import ActivityVerb

    if not policies.can_create_bug(membership):
        raise BugPermissionDenied()

    locked_project = Project.objects.select_for_update().get(pk=project.pk)
    if locked_project.archived_at is not None:
        raise ProjectArchivedForBugCreation()

    number = locked_project.next_bug_number
    locked_project.next_bug_number = number + 1
    locked_project.save(update_fields=["next_bug_number"])

    bug = Bug.objects.create(
        organization=organization,
        project=locked_project,
        number=number,
        key=f"{locked_project.key}-{number}",
        title=title,
        description=description,
        steps_to_reproduce=steps_to_reproduce,
        expected_result=expected_result,
        actual_result=actual_result,
        environment=environment,
        category=category,
        priority=priority,
        severity=severity,
        due_date=due_date,
        reporter=reporter,
    )
    _record(bug, reporter, ActivityVerb.CREATED, to_value=bug.key)
    return bug


# -- content update --------------------------------------------------------


def update_bug(*, bug: Bug, actor, membership, expected_version: int, **fields) -> Bug:
    from apps.activities.models import ActivityVerb

    with transaction.atomic():
        locked = _lock_bug(bug)
        _check_version(locked, expected_version)
        _check_mutable(locked)

        allowed = policies.editable_fields_for(locked, membership)
        if not set(fields).issubset(allowed):
            raise BugPermissionDenied()

        changed = {}
        for field, value in fields.items():
            if getattr(locked, field) != value:
                changed[field] = (getattr(locked, field), value)
                setattr(locked, field, value)

        if not changed:
            return locked

        locked.version += 1
        locked.save(update_fields=[*changed.keys(), "version"])

        for field, (old, new) in changed.items():
            if field == "priority":
                verb = ActivityVerb.PRIORITY_CHANGED
            elif field == "severity":
                verb = ActivityVerb.SEVERITY_CHANGED
            else:
                verb = ActivityVerb.FIELD_UPDATED
            _record(
                locked,
                actor,
                verb,
                from_value=str(old) if old not in (None, "") else "",
                to_value=str(new) if new not in (None, "") else "",
                metadata={"field": field} if verb == ActivityVerb.FIELD_UPDATED else None,
            )
    return locked


# -- workflow transitions --------------------------------------------------


def _validate_duplicate_target(bug: Bug, duplicate_of_id) -> Bug:
    target = (
        Bug.objects.filter(organization=bug.organization, pk=duplicate_of_id)
        .select_related("project")
        .first()
    )
    if target is None:
        raise RelatedBugNotFound()
    if target.pk == bug.pk:
        raise SelfRelationshipNotAllowed()
    if target.archived_at is not None:
        raise DuplicateTargetArchived()
    if _duplicate_chain_reaches(target, bug):
        raise DuplicateCycleDetected()
    return target


def _duplicate_chain_reaches(start_bug: Bug, needle_bug: Bug) -> bool:
    """Walks start_bug's duplicate_of chain looking for needle_bug. Returns
    True if found (linking needle -> start_bug would close a cycle).
    Raises DuplicateChainUnverifiable if the chain runs past
    MAX_DUPLICATE_CHAIN_DEPTH without terminating — that is treated as
    "cannot prove this link is safe", never as "assume it's fine"."""
    current = start_bug
    for _ in range(MAX_DUPLICATE_CHAIN_DEPTH):
        if current.pk == needle_bug.pk:
            return True
        next_rel = (
            BugRelationship.objects.filter(
                from_bug=current, relationship_type=RelationshipType.DUPLICATE_OF
            )
            .select_related("to_bug")
            .first()
        )
        if next_rel is None:
            return False
        current = next_rel.to_bug
    raise DuplicateChainUnverifiable()


def transition_bug(
    *,
    bug: Bug,
    actor,
    membership,
    new_status: str,
    expected_version: int,
    duplicate_of=None,
    assignee_id=UNSET,
) -> Bug:
    """Status transition, optionally combined atomically with an assignee
    change when the caller explicitly supplies assignee_id — the only path
    by which assignment and status ever change in the same version bump.
    Plain `assign_bug` never touches status, and this function never
    changes the assignee unless assignee_id was explicitly passed."""
    from apps.activities.models import ActivityVerb

    if new_status not in BugStatus.values:
        raise InvalidWorkflowTransition()

    with transaction.atomic():
        locked = _lock_bug(bug)
        _check_version(locked, expected_version)
        _check_mutable(locked)

        if not policies.can_change_status(locked, membership, new_status):
            raise BugPermissionDenied()
        if not workflow.is_valid_transition(locked.project, locked.status, new_status):
            raise InvalidWorkflowTransition()

        assignee = locked.assignee
        assignee_changed = False
        if assignee_id is not UNSET:
            if membership.role not in policies.STAFF_ROLES:
                raise BugPermissionDenied()
            new_assignee = _resolve_assignee(locked.organization, assignee_id)
            assignee_changed = new_assignee_id_differs(locked.assignee_id, assignee_id)
            assignee = new_assignee

        if new_status in workflow.ASSIGNEE_REQUIRED_STATUSES:
            effective_assignee = assignee if assignee_changed else locked.assignee
            if effective_assignee is None:
                raise AssigneeRequiredForTransition()

        target = None
        if new_status == BugStatus.DUPLICATE:
            if not duplicate_of:
                raise DuplicateTargetRequired()
            target = _validate_duplicate_target(locked, duplicate_of)
            try:
                BugRelationship.objects.get_or_create(
                    organization=locked.organization,
                    from_bug=locked,
                    to_bug=target,
                    relationship_type=RelationshipType.DUPLICATE_OF,
                    defaults={"created_by": actor},
                )
            except IntegrityError:
                pass  # relationship already recorded — status transition still proceeds

        from_status = locked.status
        locked.status = new_status
        workflow.apply_timestamp_side_effects(locked, new_status)

        update_fields = ["status", "resolved_at", "closed_at", "version"]
        if assignee_changed:
            locked.assignee = assignee
            update_fields.append("assignee")

        locked.version += 1
        locked.save(update_fields=update_fields)

        assigned_activity = None
        if assignee_changed:
            assigned_activity = _record(
                locked,
                actor,
                ActivityVerb.ASSIGNED if assignee else ActivityVerb.UNASSIGNED,
                to_value=assignee.email if assignee else "",
            )
        if target is not None:
            _record(
                locked,
                actor,
                ActivityVerb.RELATIONSHIP_ADDED,
                to_value=f"duplicate_of:{target.key}",
            )
        status_activity = _record(
            locked, actor, ActivityVerb.STATUS_CHANGED, from_value=from_status, to_value=new_status
        )

    # Dispatched only after the transaction above has committed — see
    # apps.notifications.services.notify, which itself defers the actual
    # Celery dispatch to transaction.on_commit. bug_reopened and
    # status_changed are mutually exclusive (never both) for the same
    # transition; bug_assigned fires only when this call actually changed
    # who's assigned, never on unassignment.
    from apps.notifications.models import NotificationEventType
    from apps.notifications.services import notify

    if assignee_changed and assignee is not None:
        notify(
            event_type=NotificationEventType.BUG_ASSIGNED,
            organization_id=locked.organization_id,
            bug_id=locked.pk,
            actor_id=actor.pk if actor else None,
            activity_id=assigned_activity.id,
            assignee_id=assignee.pk,
        )
    notify(
        event_type=(
            NotificationEventType.BUG_REOPENED
            if new_status == BugStatus.REOPENED
            else NotificationEventType.STATUS_CHANGED
        ),
        organization_id=locked.organization_id,
        bug_id=locked.pk,
        actor_id=actor.pk if actor else None,
        activity_id=status_activity.id,
    )
    return locked


def new_assignee_id_differs(current_id, new_id) -> bool:
    current = str(current_id) if current_id else None
    new = str(new_id) if new_id else None
    return current != new


# -- assignment (no status change) -----------------------------------------


def assign_bug(*, bug: Bug, actor, membership, assignee_id, expected_version: int) -> Bug:
    from apps.activities.models import ActivityVerb

    if not policies.can_assign_bug(membership):
        raise BugPermissionDenied()

    with transaction.atomic():
        locked = _lock_bug(bug)
        _check_version(locked, expected_version)
        _check_mutable(locked)

        assignee = _resolve_assignee(locked.organization, assignee_id)
        if not new_assignee_id_differs(locked.assignee_id, assignee_id):
            return locked  # already the requested assignee — no-op

        previous = locked.assignee
        locked.assignee = assignee
        locked.version += 1
        locked.save(update_fields=["assignee", "version"])

        activity = _record(
            locked,
            actor,
            ActivityVerb.ASSIGNED if assignee else ActivityVerb.UNASSIGNED,
            from_value=previous.email if previous else "",
            to_value=assignee.email if assignee else "",
        )

    if assignee is not None:
        from apps.notifications.models import NotificationEventType
        from apps.notifications.services import notify

        notify(
            event_type=NotificationEventType.BUG_ASSIGNED,
            organization_id=locked.organization_id,
            bug_id=locked.pk,
            actor_id=actor.pk if actor else None,
            activity_id=activity.id,
            assignee_id=assignee.pk,
        )
    return locked


# -- archive / restore -------------------------------------------------


def archive_bug(*, bug: Bug, actor, membership, expected_version: int) -> Bug:
    from apps.activities.models import ActivityVerb

    if not policies.can_archive_bug(membership):
        raise BugPermissionDenied()

    with transaction.atomic():
        locked = _lock_bug(bug)
        _check_version(locked, expected_version)
        if locked.project.archived_at is not None:
            raise ProjectArchivedForBugMutation()
        if locked.archived_at is not None:
            raise BugAlreadyArchived()

        locked.archived_at = timezone.now()
        locked.version += 1
        locked.save(update_fields=["archived_at", "version"])
        _record(locked, actor, ActivityVerb.ARCHIVED)
    return locked


def restore_bug(*, bug: Bug, actor, membership, expected_version: int) -> Bug:
    from apps.activities.models import ActivityVerb

    if not policies.can_archive_bug(membership):
        raise BugPermissionDenied()

    with transaction.atomic():
        locked = _lock_bug(bug)
        _check_version(locked, expected_version)
        if locked.project.archived_at is not None:
            raise ProjectArchivedForBugMutation()
        if locked.archived_at is None:
            raise BugNotArchived()

        locked.archived_at = None
        locked.version += 1
        locked.save(update_fields=["archived_at", "version"])
        _record(locked, actor, ActivityVerb.RESTORED)
    return locked


# -- tags --------------------------------------------------------------


def add_tag(*, bug: Bug, actor, membership, name: str, expected_version: int) -> Bug:
    from apps.activities.models import ActivityVerb

    normalized = normalize_tag_name(name)
    if not normalized or len(normalized) > MAX_TAG_NAME_LENGTH:
        raise InvalidTagName()
    name_key = normalized.lower()

    with transaction.atomic():
        locked = _lock_bug(bug)
        _check_version(locked, expected_version)
        _check_mutable(locked)
        if not policies.can_manage_tags(locked, membership):
            raise BugPermissionDenied()

        try:
            tag, _created = Tag.objects.get_or_create(
                organization=locked.organization,
                name_normalized=name_key,
                defaults={"name": normalized},
            )
        except IntegrityError:
            tag = Tag.objects.get(organization=locked.organization, name_normalized=name_key)

        if locked.tags.filter(pk=tag.pk).exists():
            return locked  # already tagged — idempotent no-op, no version bump

        locked.tags.add(tag)
        locked.version += 1
        locked.save(update_fields=["version"])
        _record(locked, actor, ActivityVerb.TAG_ADDED, to_value=tag.name)
    return locked


def remove_tag(*, bug: Bug, actor, membership, tag_id, expected_version: int) -> Bug:
    from apps.activities.models import ActivityVerb

    with transaction.atomic():
        locked = _lock_bug(bug)
        _check_version(locked, expected_version)
        _check_mutable(locked)
        if not policies.can_manage_tags(locked, membership):
            raise BugPermissionDenied()

        tag = Tag.objects.filter(organization=locked.organization, pk=tag_id).first()
        if tag is None or not locked.tags.filter(pk=tag.pk).exists():
            return locked  # already absent — idempotent no-op

        locked.tags.remove(tag)
        locked.version += 1
        locked.save(update_fields=["version"])
        _record(locked, actor, ActivityVerb.TAG_REMOVED, from_value=tag.name)
    return locked


# -- watchers (user-specific, no version/activity involvement) -------------


def watch_bug(*, bug: Bug, user) -> Bug:
    bug.watchers.add(user)
    return bug


def unwatch_bug(*, bug: Bug, user) -> Bug:
    bug.watchers.remove(user)
    return bug


# -- relationships (blocks / relates_to; duplicate_of only via transition_bug) --


def create_relationship(
    *, bug: Bug, actor, membership, related_bug_id, relationship_type: str, expected_version: int
) -> Bug:
    from apps.activities.models import ActivityVerb

    if relationship_type == RelationshipType.DUPLICATE_OF:
        raise InvalidRelationshipType()
    if not policies.can_manage_relationships(membership):
        raise BugPermissionDenied()

    with transaction.atomic():
        locked = _lock_bug(bug)
        _check_version(locked, expected_version)
        _check_mutable(locked)

        target = Bug.objects.filter(organization=locked.organization, pk=related_bug_id).first()
        if target is None:
            raise RelatedBugNotFound()
        if target.pk == locked.pk:
            raise SelfRelationshipNotAllowed()

        from_bug, to_bug = locked, target
        if relationship_type == RelationshipType.RELATES_TO:
            # Symmetric: canonicalize by id so "A relates_to B" and
            # "B relates_to A" can never coexist as separate rows.
            from_bug, to_bug = sorted([locked, target], key=lambda b: str(b.pk))

        try:
            _relationship, created = BugRelationship.objects.get_or_create(
                organization=locked.organization,
                from_bug=from_bug,
                to_bug=to_bug,
                relationship_type=relationship_type,
                defaults={"created_by": actor},
            )
        except IntegrityError as exc:
            raise DuplicateBugRelationship() from exc
        if not created:
            raise DuplicateBugRelationship()

        locked.version += 1
        locked.save(update_fields=["version"])
        _record(
            locked,
            actor,
            ActivityVerb.RELATIONSHIP_ADDED,
            to_value=f"{relationship_type}:{target.key}",
        )
    return locked


def remove_relationship(
    *, bug: Bug, actor, membership, relationship_id, expected_version: int
) -> Bug:
    from apps.activities.models import ActivityVerb

    if not policies.can_manage_relationships(membership):
        raise BugPermissionDenied()

    with transaction.atomic():
        locked = _lock_bug(bug)
        _check_version(locked, expected_version)
        _check_mutable(locked)

        relationship = (
            BugRelationship.objects.filter(organization=locked.organization, pk=relationship_id)
            .filter(Q(from_bug=locked) | Q(to_bug=locked))
            .select_related("from_bug", "to_bug")
            .first()
        )
        if relationship is None:
            raise RelationshipNotFound()

        other = (
            relationship.to_bug if relationship.from_bug_id == locked.pk else relationship.from_bug
        )
        relationship_type = relationship.relationship_type
        relationship.delete()

        locked.version += 1
        locked.save(update_fields=["version"])
        _record(
            locked,
            actor,
            ActivityVerb.RELATIONSHIP_REMOVED,
            from_value=f"{relationship_type}:{other.key}",
        )
    return locked


# -- membership removal integration ----------------------------------------


def clear_bug_assignments(*, organization, user) -> int:
    """Called from apps.organizations.services.remove_member, inside that
    function's own transaction, via a function-local import there (mirrors
    apps.projects.services.clear_project_leadership) — keeps apps.bugs and
    apps.organizations from needing a module-level dependency on each other.

    Bulk-safe: one UPDATE clears every affected bug's assignee in a single
    statement, and one bulk_create writes the activity trail — no per-bug
    create() in a Python loop, which would cost one extra round trip per
    bug for an org where the removed member held many open assignments.
    """
    from apps.activities.models import ActivityVerb
    from apps.activities.services import record_bug_activities_bulk

    affected_ids = list(
        Bug.objects.filter(organization=organization, assignee=user).values_list("id", flat=True)
    )
    if not affected_ids:
        return 0

    Bug.objects.filter(id__in=affected_ids).update(assignee=None, version=F("version") + 1)

    affected_bugs = Bug.objects.filter(id__in=affected_ids).select_related("organization")
    entries = [
        {
            "bug": affected_bug,
            "actor": None,
            "verb": ActivityVerb.UNASSIGNED,
            "from_value": user.email,
            "metadata": {"reason": "membership_removed"},
        }
        for affected_bug in affected_bugs
    ]
    record_bug_activities_bulk(entries)
    return len(affected_ids)
