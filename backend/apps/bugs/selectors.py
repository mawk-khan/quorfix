from django.db.models import Case, Exists, IntegerField, OuterRef, Q, QuerySet, Value, When

from apps.bugs.models import Bug, BugPriority, BugRelationship, BugSeverity, Tag
from apps.organizations.models import OrganizationMembership

# Explicit business ordering, not alphabetical — "urgent" must sort above
# "low", "blocker" above "trivial", regardless of enum declaration order.
_PRIORITY_RANK = {
    BugPriority.LOW: 0,
    BugPriority.MEDIUM: 1,
    BugPriority.HIGH: 2,
    BugPriority.URGENT: 3,
}
_SEVERITY_RANK = {
    BugSeverity.TRIVIAL: 0,
    BugSeverity.MINOR: 1,
    BugSeverity.MAJOR: 2,
    BugSeverity.CRITICAL: 3,
    BugSeverity.BLOCKER: 4,
}

SORT_FIELDS = frozenset({"created_at", "updated_at", "due_date", "number", "priority", "severity"})


def _rank_case(field: str, rank_map: dict) -> Case:
    return Case(
        *[When(**{field: value}, then=Value(rank)) for value, rank in rank_map.items()],
        output_field=IntegerField(),
    )


def get_bugs_for_organization(organization) -> QuerySet[Bug]:
    """Unfiltered organization-scoped queryset for single-object lookups
    (get_object_or_404) — mirrors apps.projects.selectors."""
    return Bug.objects.filter(organization=organization)


def _bug_detail_base(organization) -> QuerySet[Bug]:
    return get_bugs_for_organization(organization).select_related("project", "reporter", "assignee")


def get_bug_for_organization(organization, *, viewer=None) -> QuerySet[Bug]:
    """select_related version for retrieve/detail-shaped lookups (not the
    bare version used by mutating services, which lock the row instead).
    Annotates is_watching for `viewer` via Exists() rather than loading the
    watchers M2M, so checking "do I watch this" never pulls every watcher."""
    qs = _bug_detail_base(organization)
    if viewer is not None:
        watching = Bug.objects.filter(pk=OuterRef("pk"), watchers=viewer)
        qs = qs.annotate(is_watching=Exists(watching))
    return qs


def list_bugs(  # noqa: C901 - one query-serializer's worth of independent filters, not complex branching
    organization,
    *,
    viewer,
    project: str | None = None,
    statuses: list[str] | None = None,
    priority: str | None = None,
    severity: str | None = None,
    assignee: str | None = None,
    reporter: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    created_after=None,
    created_before=None,
    updated_after=None,
    updated_before=None,
    due_after=None,
    due_before=None,
    overdue: bool = False,
    unassigned: bool = False,
    watched_by_me: bool = False,
    archived: str = "false",
    search: str | None = None,
    ordering: str = "-created_at",
) -> QuerySet[Bug]:
    """Organization-scoped, filtered, sorted bug queryset for the list
    endpoint. select_related covers everything the list serializer renders;
    watched_by_me is an Exists() annotation rather than a prefetch of the
    full watchers M2M, so list rows stay O(1) queries regardless of how
    many people watch each bug."""
    qs = _bug_detail_base(organization)

    if watched_by_me and viewer is not None:
        qs = qs.filter(watchers=viewer)

    watching = (
        Bug.objects.filter(pk=OuterRef("pk"), watchers=viewer) if viewer is not None else None
    )
    if watching is not None:
        qs = qs.annotate(is_watching=Exists(watching))

    if archived == "true":
        qs = qs.filter(archived_at__isnull=False)
    elif archived == "false":
        qs = qs.filter(archived_at__isnull=True)
    # "all" applies no archived_at filter.

    if project:
        qs = qs.filter(project_id=project)
    if statuses:
        qs = qs.filter(status__in=statuses)
    if priority:
        qs = qs.filter(priority=priority)
    if severity:
        qs = qs.filter(severity=severity)
    if assignee:
        qs = qs.filter(assignee_id=assignee)
    if reporter:
        qs = qs.filter(reporter_id=reporter)
    if category:
        qs = qs.filter(category__iexact=category.strip())
    if tags:
        normalized = [t.strip().lower() for t in tags if t.strip()]
        if normalized:
            qs = qs.filter(tags__name_normalized__in=normalized).distinct()
    if created_after:
        qs = qs.filter(created_at__gte=created_after)
    if created_before:
        qs = qs.filter(created_at__lte=created_before)
    if updated_after:
        qs = qs.filter(updated_at__gte=updated_after)
    if updated_before:
        qs = qs.filter(updated_at__lte=updated_before)
    if due_after:
        qs = qs.filter(due_date__gte=due_after)
    if due_before:
        qs = qs.filter(due_date__lte=due_before)
    if overdue:
        from django.utils import timezone

        qs = qs.filter(due_date__lt=timezone.localdate())
    if unassigned:
        qs = qs.filter(assignee__isnull=True)

    search = (search or "").strip()
    if search:
        qs = qs.filter(
            Q(title__icontains=search) | Q(key__iexact=search) | Q(key__icontains=search)
        )

    return _apply_ordering(qs, ordering)


def _apply_ordering(qs: QuerySet[Bug], ordering: str) -> QuerySet[Bug]:
    descending = ordering.startswith("-")
    field = ordering[1:] if descending else ordering

    if field == "priority":
        qs = qs.annotate(_priority_rank=_rank_case("priority", _PRIORITY_RANK))
        return qs.order_by("-_priority_rank" if descending else "_priority_rank", "-created_at")
    if field == "severity":
        qs = qs.annotate(_severity_rank=_rank_case("severity", _SEVERITY_RANK))
        return qs.order_by("-_severity_rank" if descending else "_severity_rank", "-created_at")
    return qs.order_by(ordering, "-id")


def is_eligible_assignee(organization, user_id) -> bool:
    from apps.bugs.policies import ASSIGNABLE_ROLES

    return OrganizationMembership.objects.filter(
        organization=organization, user_id=user_id, role__in=ASSIGNABLE_ROLES
    ).exists()


def get_tag(organization, tag_id):
    return Tag.objects.filter(organization=organization, pk=tag_id).first()


def get_relationship(organization, relationship_id):
    return BugRelationship.objects.filter(organization=organization, pk=relationship_id).first()


def list_bug_relationships(bug) -> list[dict]:
    """Every relationship row touching this bug, from this bug's point of
    view — a stored `blocks` or `duplicate_of` row is directional, so the
    reverse side ("blocked_by", "duplicated_by") is derived here rather
    than ever being stored as its own row."""
    from apps.bugs.models import RelationshipType

    rels = (
        BugRelationship.objects.filter(organization=bug.organization)
        .filter(Q(from_bug=bug) | Q(to_bug=bug))
        .select_related("from_bug", "to_bug")
        .order_by("-created_at")
    )

    results = []
    for rel in rels:
        is_forward = rel.from_bug_id == bug.pk
        if rel.relationship_type == RelationshipType.DUPLICATE_OF:
            display_type = "duplicate_of" if is_forward else "duplicated_by"
        elif rel.relationship_type == RelationshipType.BLOCKS:
            display_type = "blocks" if is_forward else "blocked_by"
        else:
            display_type = RelationshipType.RELATES_TO
        other = rel.to_bug if is_forward else rel.from_bug
        results.append({"id": rel.id, "type": display_type, "bug": other})
    return results
