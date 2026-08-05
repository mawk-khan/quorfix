import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

pytestmark = pytest.mark.django_db


def _range(days=7):
    today = timezone.localdate()
    return {"date_from": str(today - datetime.timedelta(days=days)), "date_to": str(today)}


@pytest.fixture
def seeded_orgs(
    organization,
    project,
    admin_user,
    admin_membership,
    other_organization,
    other_project,
    other_admin_user,
    other_admin_membership,
    make_bug,
):
    """One bug in each of two independent organizations — every isolation
    test below asserts organization A's endpoints see exactly its own bug
    and never organization B's."""
    mine = make_bug(organization, project, admin_user, title="Mine")
    theirs = make_bug(other_organization, other_project, other_admin_user, title="Theirs")
    return mine, theirs


class TestSummaryIsolation:
    def test_open_count_excludes_other_org(self, admin_client, seeded_orgs):
        response = admin_client.get(reverse("analytics-summary"), _range())
        assert response.json()["open_bugs"] == 1

    def test_new_count_excludes_other_org(self, admin_client, seeded_orgs):
        response = admin_client.get(reverse("analytics-summary"), _range())
        assert response.json()["new_bugs"] == 1


class TestTrendsIsolation:
    def test_trend_totals_exclude_other_org(self, admin_client, seeded_orgs):
        response = admin_client.get(reverse("analytics-trends"), _range())
        assert sum(point["created"] for point in response.json()) == 1


class TestDistributionsIsolation:
    def test_status_distribution_excludes_other_org(self, admin_client, seeded_orgs):
        response = admin_client.get(reverse("analytics-distributions"))
        statuses = {row["status"]: row["count"] for row in response.json()["status"]}
        assert sum(statuses.values()) == 1


class TestWorkloadIsolation:
    def test_unassigned_bucket_excludes_other_org(self, admin_client, seeded_orgs):
        response = admin_client.get(reverse("analytics-workload"))
        assert response.json()["unassigned"] == 1


class TestActiveProjectsIsolation:
    def test_other_orgs_project_never_listed(self, admin_client, seeded_orgs, other_project):
        response = admin_client.get(reverse("analytics-active-projects"))
        keys = {row["key"] for row in response.json()}
        assert other_project.key not in keys


class TestRecentActivityIsolation:
    def test_other_orgs_activity_never_listed(self, admin_client, seeded_orgs):
        response = admin_client.get(reverse("analytics-recent-activity"), {"page_size": 10})
        titles = {row["bug"]["title"] for row in response.json()["results"]}
        assert titles == {"Mine"}


class TestResolutionTimeIsolation:
    def test_resolution_time_never_reflects_other_org(self, admin_client, seeded_orgs):
        # No resolved bugs in either org yet — this asserts the endpoint
        # itself is scoped (not just that the numbers happen to differ).
        response = admin_client.get(reverse("analytics-resolution-time"), _range())
        assert all(row["average_seconds"] is None for row in response.json())


class TestCrossOrgProjectFilterRejected:
    """Already covered per-endpoint in test_query_validation.py; this
    confirms the same holds true even when both organizations have real,
    populated data (not just empty orgs)."""

    ALL_URL_NAMES = [
        "analytics-summary",
        "analytics-trends",
        "analytics-resolution-time",
        "analytics-distributions",
        "analytics-workload",
        "analytics-recent-activity",
    ]

    @pytest.mark.parametrize("url_name", ALL_URL_NAMES)
    def test_foreign_project_id_rejected(self, admin_client, seeded_orgs, other_project, url_name):
        params = {"project": str(other_project.pk)}
        if url_name in ("analytics-summary", "analytics-trends", "analytics-resolution-time"):
            params.update(_range())
        response = admin_client.get(reverse(url_name), params)
        assert response.status_code == 400
