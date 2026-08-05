from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.projects.models import Project, ProjectStatus


class DuplicateProjectKey(Exception):
    pass


class InvalidProjectLead(Exception):
    pass


class ProjectAlreadyArchived(Exception):
    pass


class ProjectNotArchived(Exception):
    pass


class ArchivedProjectNotEditable(Exception):
    """Raised when attempting to PATCH a project that is currently archived.

    Restoring uses restore_project() directly, not update_project(), so it
    is never blocked by this.
    """

    pass


def normalize_project_key(raw_key: str) -> str:
    return raw_key.strip().upper()


@transaction.atomic
def create_project(
    *,
    organization,
    name: str,
    key: str,
    description: str = "",
    status: str = ProjectStatus.ACTIVE,
    lead=None,
) -> Project:
    """The serializer pre-checks key uniqueness, but two concurrent requests
    can both pass that check before either commits — the DB's unique
    constraint is the real guard, and IntegrityError here is that race
    actually happening, translated back into the same exception the
    pre-check raises."""
    try:
        return Project.objects.create(
            organization=organization,
            name=name,
            key=key,
            description=description,
            status=status,
            lead=lead,
        )
    except IntegrityError as exc:
        raise DuplicateProjectKey() from exc


@transaction.atomic
def update_project(*, project: Project, **fields) -> Project:
    if project.archived_at is not None:
        raise ArchivedProjectNotEditable()

    for field, value in fields.items():
        setattr(project, field, value)
    project.save(update_fields=list(fields.keys()))
    return project


@transaction.atomic
def archive_project(*, project: Project) -> Project:
    if project.archived_at is not None:
        raise ProjectAlreadyArchived()

    project.archived_at = timezone.now()
    project.save(update_fields=["archived_at"])
    return project


@transaction.atomic
def restore_project(*, project: Project) -> Project:
    if project.archived_at is None:
        raise ProjectNotArchived()

    project.archived_at = None
    project.save(update_fields=["archived_at"])
    return project


def clear_project_leadership(*, organization, user) -> int:
    """Clears `lead` on every project in this organization currently led by
    `user`. Scoped to one organization so leadership of projects in other
    organizations is untouched. Called by organizations.services.remove_member
    inside its own transaction — not atomic on its own."""
    return Project.objects.filter(organization=organization, lead=user).update(lead=None)
