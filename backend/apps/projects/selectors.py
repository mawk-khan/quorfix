from django.db.models import Q, QuerySet

from apps.organizations.models import OrganizationMembership
from apps.projects.models import Project


def list_projects(
    organization, *, archived: str = "false", search: str | None = None
) -> QuerySet[Project]:
    """Organization-scoped, filtered project queryset.

    `archived` is one of "true" / "false" / "all" — already validated by the
    caller (ProjectListQuerySerializer), not raw request input.
    """
    qs = Project.objects.filter(organization=organization).select_related("lead")

    if archived == "true":
        qs = qs.filter(archived_at__isnull=False)
    elif archived == "false":
        qs = qs.filter(archived_at__isnull=True)
    # "all" applies no archived_at filter.

    search = (search or "").strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(key__icontains=search))

    return qs.order_by("name")


def get_projects_for_organization(organization) -> QuerySet[Project]:
    """Unfiltered organization-scoped queryset, for single-object lookups
    (get_object_or_404) where archived/search filtering doesn't apply."""
    return Project.objects.filter(organization=organization).select_related("lead")


def project_key_exists(organization, key: str, *, exclude_pk=None) -> bool:
    qs = Project.objects.filter(organization=organization, key=key)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def is_eligible_project_lead(organization, user_id) -> bool:
    return OrganizationMembership.objects.filter(
        organization=organization, user_id=user_id
    ).exists()
