import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from apps.bugs.models import Bug, BugStatus
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

    assert not Organization.objects.filter(slug="quorfix-demo").exists()
    assert Organization.objects.count() == 1


@pytest.mark.django_db
def test_creates_organization_members_and_projects():
    run_seed_demo()

    organization = Organization.objects.get(slug="quorfix-demo")
    assert organization.name == "Quorfix Demo"

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
    assert admin_user.check_password("QuorfixDemo2026!")

    developer_user = memberships["developer@bugfixer.local"].user
    assert developer_user.check_password("DeveloperDemo2026!")

    projects = {p.key: p for p in Project.objects.filter(organization=organization)}
    assert set(projects) == {"BFW", "MOB", "API"}

    assert projects["BFW"].name == "Quorfix Web Application"
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
def test_reuses_a_pre_rename_legacy_organization_without_renaming_or_duplicating_it():
    """A local dev database seeded before the Quorfix rebrand has an
    organization at the old "bug-fixer-demo" slug. Re-running seed_demo
    against it must find and reuse that exact organization — never create a
    second "quorfix-demo" one (Community allows only one organization, so
    that would just fail outright) and never rename the existing one out
    from under whatever the operator already has bookmarked/configured."""
    from apps.organizations.services import setup_instance

    admin_persona_email = "admin@bugfixer.local"
    user, legacy_organization, _membership = setup_instance(
        organization_name="Bug Fixer Demo",
        email=admin_persona_email,
        password="whatever-was-seeded-before",
        first_name="Demo",
        last_name="Administrator",
    )
    assert legacy_organization.slug == "bug-fixer-demo"

    run_seed_demo()

    assert Organization.objects.count() == 1
    reused = Organization.objects.get()
    assert reused.pk == legacy_organization.pk
    assert reused.slug == "bug-fixer-demo"  # not renamed to "quorfix-demo"
    assert reused.name == "Bug Fixer Demo"  # not renamed either

    # The rest of seed_demo's convergence still ran normally against the
    # reused (legacy-slugged) organization — members/projects/bugs exist.
    assert OrganizationMembership.objects.filter(organization=reused).count() == 5
    assert Project.objects.filter(organization=reused).count() == 3


@pytest.mark.django_db
class TestDemoBugs:
    def test_creates_a_reasonable_number_of_bugs_across_projects_statuses_and_people(self):
        run_seed_demo()

        organization = Organization.objects.get(slug="quorfix-demo")
        bugs = list(
            Bug.objects.filter(organization=organization).select_related(
                "project", "reporter", "assignee"
            )
        )

        assert len(bugs) == 24

        statuses = {b.status for b in bugs}
        assert len(statuses) >= 10  # meaningfully spread across the workflow, not all "new"

        priorities = {b.priority for b in bugs}
        severities = {b.severity for b in bugs}
        assert priorities == {"urgent", "high", "medium", "low"}
        assert severities == {"blocker", "critical", "major", "minor", "trivial"}

        projects_touched = {b.project.key for b in bugs}
        assert projects_touched == {"BFW", "MOB", "API"}

        assignees = {b.assignee.email for b in bugs if b.assignee is not None}
        assert len(assignees) >= 3  # developer, qa, and admin all carry workload

        unassigned = [b for b in bugs if b.assignee is None]
        assert len(unassigned) >= 3

    def test_uses_the_real_create_bug_service_numbering(self):
        run_seed_demo()

        organization = Organization.objects.get(slug="quorfix-demo")
        bfw = Project.objects.get(organization=organization, key="BFW")
        bfw_bugs = sorted(Bug.objects.filter(project=bfw), key=lambda b: b.number)

        # Sequential, gap-free, project-key-prefixed — exactly what
        # create_bug() produces; seeding never sets number/key by hand.
        assert [b.number for b in bfw_bugs] == list(range(1, len(bfw_bugs) + 1))
        assert all(b.key == f"BFW-{b.number}" for b in bfw_bugs)

    def test_duplicate_bug_is_linked_to_its_target(self):
        run_seed_demo()

        organization = Organization.objects.get(slug="quorfix-demo")
        duplicate = Bug.objects.get(
            organization=organization, title="Dashboard chart issue reported twice"
        )
        target = Bug.objects.get(
            organization=organization, title="Dashboard chart fails to render for large datasets"
        )
        assert duplicate.status == BugStatus.DUPLICATE
        assert duplicate.resolved_at is not None

        from apps.bugs.models import BugRelationship, RelationshipType

        assert BugRelationship.objects.filter(
            from_bug=duplicate, to_bug=target, relationship_type=RelationshipType.DUPLICATE_OF
        ).exists()

    def test_bugs_are_backdated_across_roughly_the_last_45_days(self):
        run_seed_demo()

        organization = Organization.objects.get(slug="quorfix-demo")
        bugs = Bug.objects.filter(organization=organization)

        ages_in_days = [(timezone.now() - b.created_at).days for b in bugs]
        assert min(ages_in_days) <= 2  # something recent
        assert max(ages_in_days) >= 35  # something well in the past
        # Not every bug landed on the same day — a real spread, not a single
        # backdated cluster.
        assert len({b.created_at.date() for b in bugs}) >= 10

    def test_has_at_least_one_overdue_bug(self):
        run_seed_demo()

        organization = Organization.objects.get(slug="quorfix-demo")
        from apps.bugs.workflow import OPEN_STATUSES

        overdue = Bug.objects.filter(
            organization=organization,
            status__in=OPEN_STATUSES,
            due_date__lt=timezone.localdate(),
        )
        assert overdue.exists()

    def test_has_a_bug_with_reopened_history(self):
        run_seed_demo()

        organization = Organization.objects.get(slug="quorfix-demo")
        from apps.activities.models import ActivityVerb

        reopened_bug_ids = Bug.objects.filter(
            organization=organization,
            activities__verb=ActivityVerb.STATUS_CHANGED,
            activities__to_value=BugStatus.REOPENED,
        ).values_list("id", flat=True)
        assert reopened_bug_ids.exists()

    def test_resolved_bugs_have_a_backdated_resolution_activity(self):
        run_seed_demo()

        organization = Organization.objects.get(slug="quorfix-demo")
        bug = Bug.objects.get(
            organization=organization,
            title="Password reset email arrives several minutes late",
        )
        assert bug.status == BugStatus.RESOLVED
        assert bug.resolved_at is not None
        assert bug.resolved_at < bug.created_at + timezone.timedelta(days=13)

        from apps.activities.models import ActivityVerb, BugActivity

        resolved_activity = BugActivity.objects.get(
            bug=bug, verb=ActivityVerb.STATUS_CHANGED, to_value=BugStatus.RESOLVED
        )
        # The activity timestamp and the field must agree — resolved_at is
        # not left at "now" while the activity is backdated, or vice versa.
        assert abs((resolved_activity.created_at - bug.resolved_at).total_seconds()) < 5

    def test_repeated_seeding_does_not_duplicate_bugs_or_disturb_numbering(self):
        run_seed_demo()

        organization = Organization.objects.get(slug="quorfix-demo")
        count_after_first_run = Bug.objects.filter(organization=organization).count()
        numbers_after_first_run = {
            (b.project.key, b.number)
            for b in Bug.objects.filter(organization=organization).select_related("project")
        }

        run_seed_demo()
        run_seed_demo()

        assert Bug.objects.filter(organization=organization).count() == count_after_first_run
        numbers_after_repeat = {
            (b.project.key, b.number)
            for b in Bug.objects.filter(organization=organization).select_related("project")
        }
        assert numbers_after_repeat == numbers_after_first_run

        # Every project's next_bug_number is exactly "how many bugs it has
        # plus one" — nothing left it inconsistent across the repeated runs.
        for project in Project.objects.filter(organization=organization):
            expected_next = Bug.objects.filter(project=project).count() + 1
            assert project.next_bug_number == expected_next


@pytest.mark.django_db
def test_is_idempotent_across_repeated_runs():
    run_seed_demo()
    run_seed_demo()
    run_seed_demo()

    assert Organization.objects.filter(slug="quorfix-demo").count() == 1
    assert OrganizationMembership.objects.count() == 5
    assert Project.objects.count() == 3


@pytest.mark.django_db
def test_reconverges_data_that_drifted_between_runs():
    run_seed_demo()

    organization = Organization.objects.get(slug="quorfix-demo")
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

    organization = Organization.objects.get(slug="quorfix-demo")
    project = Project.objects.get(organization=organization, key="API")
    archive_project(project=project)

    run_seed_demo()

    project.refresh_from_db()
    assert project.archived_at is None
    assert project.status == ProjectStatus.ON_HOLD


@pytest.mark.django_db
def test_recovers_from_a_stale_pending_invitation_left_by_an_interrupted_run():
    run_seed_demo()

    organization = Organization.objects.get(slug="quorfix-demo")
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

    assert "QuorfixDemo2026!" not in output
    assert "DeveloperDemo2026!" not in output


@pytest.mark.django_db
def test_prints_a_readable_credentials_table_when_debug_is_on():
    with override_settings(DEBUG=True):
        output = run_seed_demo()

    assert "QuorfixDemo2026!" in output
    assert "admin@bugfixer.local" in output
    assert "DEVELOPMENT-ONLY" in output.upper()
    assert "http://localhost:3000" in output
