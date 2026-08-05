import pytest

from apps.projects.models import ProjectStatus
from apps.projects.services import (
    ArchivedProjectNotEditable,
    DuplicateProjectKey,
    ProjectAlreadyArchived,
    ProjectNotArchived,
    archive_project,
    clear_project_leadership,
    create_project,
    normalize_project_key,
    restore_project,
    update_project,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("eng", "ENG"),
        (" ENG ", "ENG"),
        ("  eng123  ", "ENG123"),
    ],
)
def test_normalize_project_key(raw, expected):
    assert normalize_project_key(raw) == expected


@pytest.mark.django_db
def test_create_project(organization):
    project = create_project(organization=organization, name="Engine", key="ENG")
    assert project.organization_id == organization.pk
    assert project.key == "ENG"
    assert project.status == ProjectStatus.ACTIVE


@pytest.mark.django_db
def test_create_project_raises_on_db_level_duplicate_key(organization, make_project):
    make_project(organization, key="ENG")
    with pytest.raises(DuplicateProjectKey):
        create_project(organization=organization, name="Another Engine", key="ENG")


@pytest.mark.django_db
def test_update_project_changes_only_given_fields(organization, make_project):
    project = make_project(organization, name="Engine")
    updated = update_project(project=project, name="Engine Team")
    assert updated.name == "Engine Team"
    assert updated.key == "ENG"


@pytest.mark.django_db
def test_update_project_raises_when_archived(organization, make_project):
    project = make_project(organization)
    archive_project(project=project)
    with pytest.raises(ArchivedProjectNotEditable):
        update_project(project=project, name="New name")


@pytest.mark.django_db
def test_archive_project(organization, make_project):
    project = make_project(organization)
    archived = archive_project(project=project)
    assert archived.archived_at is not None


@pytest.mark.django_db
def test_archive_project_twice_raises(organization, make_project):
    project = make_project(organization)
    archive_project(project=project)
    with pytest.raises(ProjectAlreadyArchived):
        archive_project(project=project)


@pytest.mark.django_db
def test_restore_project(organization, make_project):
    project = make_project(organization)
    archive_project(project=project)
    restored = restore_project(project=project)
    assert restored.archived_at is None


@pytest.mark.django_db
def test_restore_project_when_not_archived_raises(organization, make_project):
    project = make_project(organization)
    with pytest.raises(ProjectNotArchived):
        restore_project(project=project)


@pytest.mark.django_db
def test_clear_project_leadership_only_affects_given_organization(
    organization, admin_user, make_project
):
    from apps.organizations.models import Organization

    other_org = Organization.objects.create(name="Other Co", slug="other-co")
    led_here = make_project(organization, key="ENG", lead=admin_user)
    led_elsewhere = make_project(other_org, key="ENG", lead=admin_user)

    cleared = clear_project_leadership(organization=organization, user=admin_user)

    led_here.refresh_from_db()
    led_elsewhere.refresh_from_db()
    assert cleared == 1
    assert led_here.lead_id is None
    assert led_elsewhere.lead_id == admin_user.pk
