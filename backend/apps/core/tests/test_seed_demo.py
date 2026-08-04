import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from apps.organizations.models import (
    CommunityRole,
    Invitation,
    Organization,
    OrganizationMembership,
    SetupLock,
)
from apps.organizations.services import create_invitation
from apps.projects.models import Project, ProjectStatus

DEMO_EMAILS = {
    "admin@bugfixer.local",
    "developer@bugfixer.local",
    "qa@bugfixer.local",
    "reporter@bugfixer.local",
    "viewer@bugfixer.local",
}


def run_seed_demo() -> str:
    out = io.StringIO()
    call_command("seed_demo", stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_refuses_to_run_under_production_settings():
    with override_settings(SETTINGS_MODULE="config.settings.production"):
        with pytest.raises(CommandError):
            call_command("seed_demo")

    assert not Organization.objects.exists()


@pytest.mark.django_db
def test_refuses_to_seed_when_a_different_organization_is_already_configured(organization):
    # `organization` (conftest.py) creates "Acme" directly, not through
    # setup_instance — mark the SetupLock completed too so is_instance_configured()
    # reflects what a real completed /setup would leave behind.
    SetupLock.objects.filter(id=1).update(completed_at=timezone.now())

    with pytest.raises(CommandError):
        call_command("seed_demo")

    assert not Organization.objects.filter(slug="bug-fixer-demo").exists()
    assert Organization.objects.count() == 1


@pytest.mark.django_db
def test_creates_organization_members_and_projects():
    run_seed_demo()

    organization = Organization.objects.get(slug="bug-fixer-demo")
    assert organization.name == "Bug Fixer Demo"

    memberships = {
        m.user.email: m
        for m in OrganizationMembership.objects.filter(organization=organization).select_related(
            "user"
        )
    }
    assert set(memberships) == DEMO_EMAILS
    assert memberships["admin@bugfixer.local"].role == CommunityRole.ADMINISTRATOR
    assert memberships["developer@bugfixer.local"].role == CommunityRole.DEVELOPER
    assert memberships["qa@bugfixer.local"].role == CommunityRole.QA
    assert memberships["reporter@bugfixer.local"].role == CommunityRole.REPORTER
    assert memberships["viewer@bugfixer.local"].role == CommunityRole.VIEWER

    admin_user = memberships["admin@bugfixer.local"].user
    assert admin_user.first_name == "Demo"
    assert admin_user.last_name == "Administrator"
    assert admin_user.check_password("BugFixerDemo2026!")

    developer_user = memberships["developer@bugfixer.local"].user
    assert developer_user.check_password("DeveloperDemo2026!")

    projects = {p.key: p for p in Project.objects.filter(organization=organization)}
    assert set(projects) == {"BFW", "MOB", "API"}

    assert projects["BFW"].name == "Bug Fixer Web Application"
    assert projects["BFW"].status == ProjectStatus.ACTIVE
    assert projects["BFW"].lead_id == admin_user.pk
    assert projects["BFW"].archived_at is None

    assert projects["MOB"].name == "Mobile Application"
    assert projects["MOB"].status == ProjectStatus.PLANNING
    assert projects["MOB"].lead_id == developer_user.pk

    assert projects["API"].name == "Legacy API"
    assert projects["API"].status == ProjectStatus.ON_HOLD
    assert projects["API"].lead_id == memberships["qa@bugfixer.local"].user.pk


@pytest.mark.django_db
def test_is_idempotent_across_repeated_runs():
    run_seed_demo()
    run_seed_demo()
    run_seed_demo()

    assert Organization.objects.filter(slug="bug-fixer-demo").count() == 1
    assert OrganizationMembership.objects.count() == 5
    assert Project.objects.count() == 3


@pytest.mark.django_db
def test_reconverges_data_that_drifted_between_runs():
    run_seed_demo()

    organization = Organization.objects.get(slug="bug-fixer-demo")
    dev_membership = OrganizationMembership.objects.select_related("user").get(
        organization=organization, user__email="developer@bugfixer.local"
    )
    dev_membership.role = CommunityRole.VIEWER
    dev_membership.save(update_fields=["role"])
    dev_membership.user.set_password("something-else")
    dev_membership.user.save(update_fields=["password"])

    project = Project.objects.get(organization=organization, key="MOB")
    project.name = "Renamed"
    project.status = ProjectStatus.COMPLETED
    project.save(update_fields=["name", "status"])

    run_seed_demo()

    dev_membership.refresh_from_db()
    dev_membership.user.refresh_from_db()
    project.refresh_from_db()

    assert dev_membership.role == CommunityRole.DEVELOPER
    assert dev_membership.user.check_password("DeveloperDemo2026!")
    assert project.name == "Mobile Application"
    assert project.status == ProjectStatus.PLANNING


@pytest.mark.django_db
def test_reconverges_an_archived_demo_project():
    run_seed_demo()

    from apps.projects.services import archive_project

    organization = Organization.objects.get(slug="bug-fixer-demo")
    project = Project.objects.get(organization=organization, key="API")
    archive_project(project=project)

    run_seed_demo()

    project.refresh_from_db()
    assert project.archived_at is None
    assert project.status == ProjectStatus.ON_HOLD


@pytest.mark.django_db
def test_recovers_from_a_stale_pending_invitation_left_by_an_interrupted_run():
    run_seed_demo()

    organization = Organization.objects.get(slug="bug-fixer-demo")
    reporter_membership = OrganizationMembership.objects.select_related("user").get(
        organization=organization, user__email="reporter@bugfixer.local"
    )
    admin_user = (
        OrganizationMembership.objects.select_related("user")
        .get(organization=organization, user__email="admin@bugfixer.local")
        .user
    )

    # Simulate a run that crashed between create_invitation() succeeding and
    # accept_invitation() completing: the membership never got created, and
    # the only invitation on record for this email is a pending, unaccepted
    # one — not the already-accepted one the initial run_seed_demo() above
    # left behind, which this clears first so it doesn't confound the count
    # assertions below.
    reporter_membership.delete()
    Invitation.objects.filter(organization=organization, email="reporter@bugfixer.local").delete()
    create_invitation(
        organization=organization,
        invited_by=admin_user,
        email="reporter@bugfixer.local",
        role=CommunityRole.REPORTER,
    )
    assert (
        Invitation.objects.filter(
            organization=organization,
            email="reporter@bugfixer.local",
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        ).count()
        == 1
    )

    run_seed_demo()

    membership = OrganizationMembership.objects.select_related("user").get(
        organization=organization, user__email="reporter@bugfixer.local"
    )
    assert membership.role == CommunityRole.REPORTER
    assert membership.user.check_password("ReporterDemo2026!")

    # The stale invitation was revoked and exactly one fresh one accepted in
    # its place — not left pending forever, not duplicated further.
    invitations = Invitation.objects.filter(
        organization=organization, email="reporter@bugfixer.local"
    )
    assert invitations.count() == 2
    assert invitations.filter(revoked_at__isnull=False).count() == 1
    assert invitations.filter(accepted_at__isnull=False).count() == 1

    # A further run must not touch invitations again for this email.
    run_seed_demo()
    assert (
        Invitation.objects.filter(
            organization=organization, email="reporter@bugfixer.local"
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_does_not_print_credentials_when_debug_is_off():
    output = run_seed_demo()

    assert "BugFixerDemo2026!" not in output
    assert "DeveloperDemo2026!" not in output


@pytest.mark.django_db
def test_prints_a_readable_credentials_table_when_debug_is_on():
    with override_settings(DEBUG=True):
        output = run_seed_demo()

    assert "BugFixerDemo2026!" in output
    assert "admin@bugfixer.local" in output
    assert "DEVELOPMENT-ONLY" in output.upper()
    assert "http://localhost:3000" in output
