import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.organizations.models import Organization, OrganizationMembership
from apps.projects.models import Project


def run() -> str:
    out = io.StringIO()
    call_command("seed_e2e_bug_fixture", stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_refuses_to_run_under_production_settings():
    with override_settings(SETTINGS_MODULE="config.settings.production"):
        with pytest.raises(CommandError):
            call_command("seed_e2e_bug_fixture")

    assert not Organization.objects.filter(slug="bug-e2e-org").exists()


@pytest.mark.django_db
def test_creates_organization_five_users_and_a_project():
    run()

    organization = Organization.objects.get(slug="bug-e2e-org")
    memberships = OrganizationMembership.objects.filter(organization=organization)
    assert memberships.count() == 5

    project = Project.objects.get(organization=organization, key="BEP")
    assert project.lead is not None
    assert project.lead.email == "bug-e2e-admin@example.com"


@pytest.mark.django_db
def test_is_idempotent():
    run()
    run()
    run()

    assert Organization.objects.filter(slug="bug-e2e-org").count() == 1
    organization = Organization.objects.get(slug="bug-e2e-org")
    assert OrganizationMembership.objects.filter(organization=organization).count() == 5
    assert Project.objects.filter(organization=organization).count() == 1


@pytest.mark.django_db
def test_does_not_collide_with_an_unrelated_organization():
    # Community allows only one org through the real /setup API, but this
    # fixture bypasses that gate deliberately (like every other test fixture
    # in this codebase that calls Organization.objects.create directly) so
    # the e2e spec never has to fight another spec file for the single
    # "first-run setup" slot.
    Organization.objects.create(name="Acme", slug="acme")

    run()

    assert Organization.objects.count() == 2
    assert Organization.objects.filter(slug="bug-e2e-org").exists()


@pytest.mark.django_db
def test_does_not_block_the_real_first_run_setup_flow():
    # This is the whole point of is_active=False: whichever spec performs
    # the actual product-facing /setup flow (team-journey.spec.ts) must
    # still be able to, regardless of whether this fixture ran first.
    from apps.organizations.services import setup_instance

    run()
    assert not Organization.objects.filter(slug="bug-e2e-org", is_active=True).exists()

    user, organization, membership = setup_instance(
        organization_name="Acme", email="admin@example.com", password="Str0ngPassw0rd!"
    )
    assert organization.slug == "acme"
    assert organization.is_active is True
