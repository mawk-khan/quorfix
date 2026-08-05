import pytest
from django.db import IntegrityError, transaction

from apps.organizations.models import Organization
from apps.projects.models import Project, ProjectStatus


@pytest.mark.django_db
def test_project_key_is_unique_per_organization(organization, make_project):
    make_project(organization, key="ENG")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_project(organization, key="ENG", name="Another Engine")


@pytest.mark.django_db
def test_same_key_is_allowed_across_different_organizations(organization, make_project):
    other_org = Organization.objects.create(name="Other Co", slug="other-co")
    make_project(organization, key="ENG")
    other_project = make_project(other_org, key="ENG")
    assert other_project.pk is not None


@pytest.mark.django_db
def test_key_must_be_uppercase_at_the_database_level(organization):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Project.objects.create(organization=organization, key="eng", name="Engine")


@pytest.mark.django_db
def test_lead_is_cleared_when_the_user_is_deleted(organization, admin_user, make_project):
    project = make_project(organization, lead=admin_user)
    admin_user.delete()
    project.refresh_from_db()
    assert project.lead_id is None


@pytest.mark.django_db
def test_default_status_is_active(organization, make_project):
    project = make_project(organization)
    assert project.status == ProjectStatus.ACTIVE


@pytest.mark.django_db
def test_archived_at_defaults_to_null(organization, make_project):
    project = make_project(organization)
    assert project.archived_at is None
