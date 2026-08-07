import io
import os

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from apps.activities.models import BugActivity
from apps.attachments.models import Attachment, AttachmentStatus
from apps.bugs.models import Bug
from apps.bugs.workflow import OPEN_STATUSES, RESOLUTION_STATUSES
from apps.core.management.commands.generate_perf_dataset import PERF_EMAIL_DOMAIN, PERF_SLUG_PREFIX
from apps.organizations.models import CommunityRole, Organization, OrganizationMembership, SetupLock
from apps.projects.models import Project


def run(disposable=True, **kwargs):
    """Invokes generate_perf_dataset with BUGFIXER_DISPOSABLE_DATABASE set
    (or deliberately absent, for disposable=False guard tests) — restoring
    whatever the environment variable's prior value was afterward, so one
    test's env mutation can never leak into the next."""
    out = io.StringIO()
    args = []
    for key, value in kwargs.items():
        flag = "--" + key.replace("_", "-")
        args.append(flag)
        if value is not True:
            args.append(str(value))

    previous = os.environ.get("BUGFIXER_DISPOSABLE_DATABASE")
    try:
        if disposable:
            os.environ["BUGFIXER_DISPOSABLE_DATABASE"] = "true"
        elif "BUGFIXER_DISPOSABLE_DATABASE" in os.environ:
            del os.environ["BUGFIXER_DISPOSABLE_DATABASE"]
        call_command("generate_perf_dataset", *args, stdout=out)
    finally:
        if previous is None:
            os.environ.pop("BUGFIXER_DISPOSABLE_DATABASE", None)
        else:
            os.environ["BUGFIXER_DISPOSABLE_DATABASE"] = previous
    return out.getvalue()


def run_cleanup() -> str:
    out = io.StringIO()
    previous = os.environ.get("BUGFIXER_DISPOSABLE_DATABASE")
    os.environ["BUGFIXER_DISPOSABLE_DATABASE"] = "true"
    try:
        call_command(
            "generate_perf_dataset",
            "--cleanup-existing-perf-data",
            "--confirm-disposable-database",
            stdout=out,
        )
    finally:
        if previous is None:
            os.environ.pop("BUGFIXER_DISPOSABLE_DATABASE", None)
        else:
            os.environ["BUGFIXER_DISPOSABLE_DATABASE"] = previous
    return out.getvalue()


TINY_KWARGS = dict(
    seed=1,
    organizations=1,
    projects_per_organization=2,
    users_per_organization=4,
    bugs_per_organization=30,
)


# -- safety guards ------------------------------------------------------------


@pytest.mark.django_db
def test_refuses_to_run_under_production_environment():
    with override_settings(ENVIRONMENT="production"):
        with pytest.raises(CommandError, match="production"):
            run(**TINY_KWARGS)
    assert not Organization.objects.filter(slug__startswith=PERF_SLUG_PREFIX).exists()


@pytest.mark.django_db
def test_refuses_without_disposable_database_flag():
    with pytest.raises(CommandError, match="BUGFIXER_DISPOSABLE_DATABASE"):
        run(disposable=False, **TINY_KWARGS)
    assert not Organization.objects.filter(slug__startswith=PERF_SLUG_PREFIX).exists()


@pytest.mark.django_db
def test_refuses_when_database_name_looks_like_production():
    from django.db import connection

    original_name = connection.settings_dict["NAME"]
    connection.settings_dict["NAME"] = "quorfix_prod"
    try:
        with pytest.raises(CommandError, match="prod"):
            run(**TINY_KWARGS)
    finally:
        connection.settings_dict["NAME"] = original_name
    assert not Organization.objects.filter(slug__startswith=PERF_SLUG_PREFIX).exists()


@pytest.mark.django_db
def test_refuses_when_demo_organization_present():
    Organization.objects.create(name="Quorfix Demo", slug="quorfix-demo")
    with pytest.raises(CommandError, match="demo"):
        run(**TINY_KWARGS)
    assert not Organization.objects.filter(slug__startswith=PERF_SLUG_PREFIX).exists()


@pytest.mark.django_db
def test_refuses_when_legacy_pre_rename_demo_organization_present():
    """PROTECTED_ORG_SLUGS still recognizes the pre-Quorfix-rebrand slug —
    a local dev database seeded before the rename must stay just as
    protected as one seeded after it."""
    Organization.objects.create(name="Bug Fixer Demo", slug="bug-fixer-demo")
    with pytest.raises(CommandError, match="demo"):
        run(**TINY_KWARGS)
    assert not Organization.objects.filter(slug__startswith=PERF_SLUG_PREFIX).exists()


@pytest.mark.django_db
def test_refuses_when_e2e_fixture_organization_present():
    Organization.objects.create(name="Bug E2E Org", slug="bug-e2e-org")
    with pytest.raises(CommandError):
        run(**TINY_KWARGS)
    assert not Organization.objects.filter(slug__startswith=PERF_SLUG_PREFIX).exists()


@pytest.mark.django_db
def test_full_profile_requires_confirm_disposable_database_flag():
    with pytest.raises(CommandError, match="confirm-disposable-database"):
        run(
            full=True,
            organizations=1,
            projects_per_organization=1,
            users_per_organization=2,
            bugs_per_organization=1,
        )
    assert not Organization.objects.filter(slug__startswith=PERF_SLUG_PREFIX).exists()


@pytest.mark.django_db
def test_cleanup_requires_confirm_disposable_database_flag():
    with pytest.raises(CommandError, match="confirm-disposable-database"):
        run(cleanup_existing_perf_data=True)


# -- generation correctness ----------------------------------------------


@pytest.mark.django_db
def test_default_profile_argument_defaults_match_spec():
    from apps.core.management.commands.generate_perf_dataset import DEFAULT_PROFILE

    assert DEFAULT_PROFILE["organizations"] == 1
    assert DEFAULT_PROFILE["projects_per_organization"] == 5
    assert DEFAULT_PROFILE["users_per_organization"] == 10
    assert DEFAULT_PROFILE["bugs_per_organization"] == 1_000


@pytest.mark.django_db
def test_full_profile_matches_spec():
    from apps.core.management.commands.generate_perf_dataset import FULL_PROFILE

    assert FULL_PROFILE["organizations"] == 5
    assert FULL_PROFILE["organizations"] * FULL_PROFILE["projects_per_organization"] == 100
    assert FULL_PROFILE["organizations"] * FULL_PROFILE["bugs_per_organization"] == 100_000


@pytest.mark.django_db
def test_configurable_counts_are_respected():
    run(
        seed=2,
        organizations=1,
        projects_per_organization=1,
        users_per_organization=3,
        bugs_per_organization=17,
    )
    org = Organization.objects.get(slug__startswith=PERF_SLUG_PREFIX)
    assert OrganizationMembership.objects.filter(organization=org).count() == 3
    assert Project.objects.filter(organization=org).count() == 1
    assert Bug.objects.filter(organization=org).count() == 17


@pytest.mark.django_db
def test_batch_size_does_not_change_the_generated_count():
    run(
        seed=3,
        organizations=1,
        projects_per_organization=1,
        users_per_organization=2,
        bugs_per_organization=25,
        batch_size=4,
    )
    org = Organization.objects.get(slug__startswith=PERF_SLUG_PREFIX)
    assert Bug.objects.filter(organization=org).count() == 25


@pytest.mark.django_db
def test_project_bug_numbering_is_sequential_and_next_bug_number_advances():
    run(**TINY_KWARGS)
    org = Organization.objects.get(slug__startswith=PERF_SLUG_PREFIX)
    for project in Project.objects.filter(organization=org):
        numbers = list(
            Bug.objects.filter(project=project).order_by("number").values_list("number", flat=True)
        )
        assert numbers == list(range(1, len(numbers) + 1))
        assert project.next_bug_number == len(numbers) + 1
        for bug in Bug.objects.filter(project=project):
            assert bug.key == f"{project.key}-{bug.number}"


@pytest.mark.django_db
def test_generated_organization_has_exactly_one_administrator():
    run(**TINY_KWARGS)
    org = Organization.objects.get(slug__startswith=PERF_SLUG_PREFIX)
    assert (
        OrganizationMembership.objects.filter(
            organization=org, role=CommunityRole.ADMINISTRATOR
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_bug_reporters_and_assignees_are_real_org_members():
    run(**TINY_KWARGS)
    org = Organization.objects.get(slug__startswith=PERF_SLUG_PREFIX)
    member_ids = set(
        OrganizationMembership.objects.filter(organization=org).values_list("user_id", flat=True)
    )
    for bug in Bug.objects.filter(organization=org):
        assert bug.reporter_id in member_ids
        if bug.assignee_id is not None:
            assert bug.assignee_id in member_ids


@pytest.mark.django_db
def test_status_timestamp_invariants_hold_for_every_generated_bug():
    run(**TINY_KWARGS)
    org = Organization.objects.get(slug__startswith=PERF_SLUG_PREFIX)
    bugs = Bug.objects.filter(organization=org)
    assert bugs.exists()

    for bug in bugs:
        if bug.status in OPEN_STATUSES:
            assert bug.resolved_at is None
            assert bug.closed_at is None
        elif bug.status == "reopened":
            assert bug.resolved_at is None
            assert bug.closed_at is None
        elif bug.status in RESOLUTION_STATUSES:
            assert bug.resolved_at is not None
            assert bug.closed_at is None
        elif bug.status == "closed":
            assert bug.resolved_at is not None
            assert bug.closed_at is not None
            assert bug.closed_at >= bug.resolved_at


@pytest.mark.django_db
def test_every_bug_has_at_least_one_created_activity():
    run(**TINY_KWARGS)
    org = Organization.objects.get(slug__startswith=PERF_SLUG_PREFIX)
    for bug in Bug.objects.filter(organization=org):
        assert BugActivity.objects.filter(bug=bug, verb="created").exists()


@pytest.mark.django_db
def test_attachment_rows_are_metadata_only_and_never_visible_or_downloadable():
    run(
        seed=4,
        organizations=1,
        projects_per_organization=1,
        users_per_organization=3,
        bugs_per_organization=40,
        attachment_rate=1.0,
    )
    org = Organization.objects.get(slug__startswith=PERF_SLUG_PREFIX)
    attachments = Attachment.objects.filter(organization=org)
    assert attachments.exists()
    for attachment in attachments:
        assert attachment.status == AttachmentStatus.FAILED
        assert attachment.uploaded_at is None
        assert attachment.removed_at is None
        assert attachment.failed_at is not None
        assert attachment.size_bytes > 0

    from apps.attachments.selectors import list_attachments_for_bug

    for bug in Bug.objects.filter(organization=org, attachments__isnull=False).distinct():
        assert not list_attachments_for_bug(bug).exists()


@pytest.mark.django_db
def test_generated_users_use_the_perf_email_domain():
    run(**TINY_KWARGS)
    org = Organization.objects.get(slug__startswith=PERF_SLUG_PREFIX)
    for membership in OrganizationMembership.objects.filter(organization=org).select_related(
        "user"
    ):
        assert membership.user.email.endswith(f"@{PERF_EMAIL_DOMAIN}")


@pytest.mark.django_db
def test_repeated_seeded_run_produces_identical_bug_status_distribution():
    out1 = run(**TINY_KWARGS)
    run_cleanup()
    out2 = run(**TINY_KWARGS)

    def distribution_lines(output: str) -> list[str]:
        return [line for line in output.splitlines() if ":" in line and "%" in line]

    assert distribution_lines(out1) == distribution_lines(out2)


@pytest.mark.django_db
def test_multiple_organizations_stay_isolated_from_each_other():
    run(
        seed=5,
        organizations=2,
        projects_per_organization=1,
        users_per_organization=3,
        bugs_per_organization=10,
    )
    orgs = list(Organization.objects.filter(slug__startswith=PERF_SLUG_PREFIX).order_by("slug"))
    assert len(orgs) == 2

    org_a, org_b = orgs
    users_a = set(
        OrganizationMembership.objects.filter(organization=org_a).values_list("user_id", flat=True)
    )
    users_b = set(
        OrganizationMembership.objects.filter(organization=org_b).values_list("user_id", flat=True)
    )
    assert users_a.isdisjoint(users_b)

    for bug in Bug.objects.filter(organization=org_a):
        assert bug.project.organization_id == org_a.id
        assert bug.reporter_id in users_a


# -- cleanup ------------------------------------------------------------


@pytest.mark.django_db
def test_cleanup_removes_only_perf_owned_organizations():
    other = Organization.objects.create(name="Acme", slug="acme")

    run(**TINY_KWARGS)
    assert Organization.objects.filter(slug=other.slug).exists()

    run_cleanup()

    assert not Organization.objects.filter(slug__startswith=PERF_SLUG_PREFIX).exists()
    assert Organization.objects.filter(slug=other.slug).exists()


@pytest.mark.django_db
def test_cleanup_refuses_outright_when_demo_organization_present(admin_user, make_membership):
    """The safety guard in _check_safety runs before branching into either
    generation or cleanup — so cleanup can never even *attempt* to run
    against a database containing demo/E2E data, not merely "run but skip
    them". Stronger than scoping the delete alone would be: a perf-owned
    organization present alongside a demo organization stays completely
    untouched, because the whole command refuses before touching anything."""
    demo_org = Organization.objects.create(name="Bug Fixer Demo", slug="bug-fixer-demo")
    make_membership(demo_org, admin_user, role=CommunityRole.ADMINISTRATOR)
    SetupLock.objects.filter(id=1).update(completed_at=timezone.now())
    perf_org = Organization.objects.create(name="Performance Org 1", slug="perf-001")

    with pytest.raises(CommandError, match="protected organization"):
        run_cleanup()

    assert Organization.objects.filter(pk=perf_org.pk).exists()
    assert Organization.objects.filter(pk=demo_org.pk).exists()


@pytest.mark.django_db
def test_cleanup_with_no_perf_data_is_a_safe_no_op():
    out = io.StringIO()
    import os

    os.environ["BUGFIXER_DISPOSABLE_DATABASE"] = "true"
    try:
        call_command(
            "generate_perf_dataset",
            "--cleanup-existing-perf-data",
            "--confirm-disposable-database",
            stdout=out,
        )
    finally:
        del os.environ["BUGFIXER_DISPOSABLE_DATABASE"]
    assert "nothing to clean up" in out.getvalue().lower()
