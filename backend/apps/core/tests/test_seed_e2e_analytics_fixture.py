import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from apps.bugs.models import Bug
from apps.bugs.workflow import OPEN_STATUSES
from apps.organizations.models import Organization, OrganizationMembership

EXPECTED_EMAILS = {
    "analytics-e2e-admin@example.com",
    "analytics-e2e-developer@example.com",
    "analytics-e2e-qa@example.com",
    "analytics-e2e-reporter@example.com",
    "analytics-e2e-viewer@example.com",
}


def run_fixture() -> str:
    out = io.StringIO()
    call_command("seed_e2e_analytics_fixture", stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_refuses_to_run_under_production_settings():
    with override_settings(SETTINGS_MODULE="config.settings.production"):
        with pytest.raises(CommandError):
            call_command("seed_e2e_analytics_fixture")
    assert not Organization.objects.filter(slug="analytics-e2e-org").exists()


@pytest.mark.django_db
def test_creates_isolated_organization_and_personas():
    run_fixture()

    organization = Organization.objects.get(slug="analytics-e2e-org")
    assert organization.is_active is False  # invisible to the single-active-org check

    emails = set(
        OrganizationMembership.objects.filter(organization=organization).values_list(
            "user__email", flat=True
        )
    )
    assert emails == EXPECTED_EMAILS


@pytest.mark.django_db
def test_is_idempotent():
    run_fixture()
    organization = Organization.objects.get(slug="analytics-e2e-org")
    count_after_first = Bug.objects.filter(organization=organization).count()

    run_fixture()
    run_fixture()

    assert Bug.objects.filter(organization=organization).count() == count_after_first
    assert Organization.objects.filter(slug="analytics-e2e-org").count() == 1


@pytest.mark.django_db
def test_does_not_touch_other_organizations(
    organization, project, admin_user, admin_membership, make_bug
):
    make_bug(organization, project, admin_user, title="Unrelated bug")
    run_fixture()

    # The unrelated org's bug is untouched, and the fixture's own bugs never
    # land in it.
    assert Bug.objects.filter(organization=organization).count() == 1
    fixture_org = Organization.objects.get(slug="analytics-e2e-org")
    assert not Bug.objects.filter(organization=fixture_org, title="Unrelated bug").exists()


@pytest.mark.django_db
class TestExpectedDashboardValues:
    """Cross-checks every number documented in the FIXTURE_BUGS module
    docstring — if either drifts, this catches it before the Playwright
    spec does, with a much faster feedback loop."""

    def test_bug_count_and_open_count(self):
        run_fixture()
        organization = Organization.objects.get(slug="analytics-e2e-org")
        bugs = Bug.objects.filter(organization=organization)
        assert bugs.count() == 8
        assert bugs.filter(status__in=OPEN_STATUSES).count() == 5

    def test_overdue_count(self):
        run_fixture()
        organization = Organization.objects.get(slug="analytics-e2e-org")
        overdue = Bug.objects.filter(
            organization=organization, status__in=OPEN_STATUSES, due_date__lt=timezone.localdate()
        )
        assert overdue.count() == 1

    def test_created_at_spread_matches_documented_offsets(self):
        run_fixture()
        organization = Organization.objects.get(slug="analytics-e2e-org")
        ages_in_days = sorted(
            (timezone.now() - b.created_at).days
            for b in Bug.objects.filter(organization=organization)
        )
        within_seven_days = [age for age in ages_in_days if age <= 6]
        outside_seven_days = [age for age in ages_in_days if age > 6]
        assert len(within_seven_days) == 6
        assert len(outside_seven_days) == 2

    def test_workload_split(self):
        run_fixture()
        organization = Organization.objects.get(slug="analytics-e2e-org")
        open_bugs = Bug.objects.filter(organization=organization, status__in=OPEN_STATUSES)
        developer = OrganizationMembership.objects.get(
            organization=organization, user__email="analytics-e2e-developer@example.com"
        ).user
        qa = OrganizationMembership.objects.get(
            organization=organization, user__email="analytics-e2e-qa@example.com"
        ).user

        assert open_bugs.filter(assignee=developer).count() == 1
        assert open_bugs.filter(assignee=qa).count() == 1
        assert open_bugs.filter(assignee__isnull=True).count() == 3
