import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bugs.models import BugStatus
from apps.bugs.services import archive_bug, transition_bug
from apps.projects.services import archive_project

pytestmark = pytest.mark.django_db


def _distributions(client, **params):
    response = client.get(reverse("analytics-distributions"), params)
    assert response.status_code == 200, response.json()
    return response.json()


class TestStatusDistribution:
    def test_all_thirteen_statuses_present_with_zero_default(self, admin_client, project):
        data = _distributions(admin_client)
        statuses = {row["status"]: row["count"] for row in data["status"]}
        assert set(statuses.keys()) == set(BugStatus.values)
        assert all(count == 0 for count in statuses.values())

    def test_counts_current_status_not_creation_status(
        self, admin_client, organization, project, admin_user, admin_membership, make_bug
    ):
        bug = make_bug(organization, project, admin_user)
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.TRIAGED,
            expected_version=bug.version,
        )
        data = _distributions(admin_client)
        statuses = {row["status"]: row["count"] for row in data["status"]}
        assert statuses[BugStatus.NEW] == 0
        assert statuses[BugStatus.TRIAGED] == 1

    def test_archived_bug_excluded(
        self, admin_client, organization, project, admin_user, admin_membership, make_bug
    ):
        bug = make_bug(organization, project, admin_user)
        archive_bug(
            bug=bug, actor=admin_user, membership=admin_membership, expected_version=bug.version
        )
        data = _distributions(admin_client)
        statuses = {row["status"]: row["count"] for row in data["status"]}
        assert sum(statuses.values()) == 0

    def test_archived_project_excluded(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user)
        archive_project(project=project)
        data = _distributions(admin_client)
        statuses = {row["status"]: row["count"] for row in data["status"]}
        assert sum(statuses.values()) == 0

    def test_project_filter_narrows_distribution(
        self, admin_client, organization, project, make_project, admin_user, make_bug
    ):
        other = make_project(organization, key="OTH4", name="Other")
        make_bug(organization, project, admin_user)
        make_bug(organization, other, admin_user)
        data = _distributions(admin_client, project=str(project.pk))
        statuses = {row["status"]: row["count"] for row in data["status"]}
        assert sum(statuses.values()) == 1

    def test_ignores_date_range_query_params(
        self, admin_client, organization, project, admin_user, make_bug, backdate_bug, days_ago
    ):
        bug = make_bug(organization, project, admin_user)
        backdate_bug(bug, created_at=days_ago(200))
        today = timezone.localdate()
        # date_from/date_to aren't even accepted by this endpoint's query
        # serializer — passing them must be harmless and must not filter
        # out a bug created long before this "range".
        data = _distributions(
            admin_client,
            date_from=str(today - datetime.timedelta(days=1)),
            date_to=str(today),
        )
        statuses = {row["status"]: row["count"] for row in data["status"]}
        assert sum(statuses.values()) == 1


class TestSeverityDistribution:
    def test_all_five_severities_present_ranked_blocker_to_trivial(self, admin_client, project):
        data = _distributions(admin_client)
        severities = [row["severity"] for row in data["severity"]]
        assert severities == ["blocker", "critical", "major", "minor", "trivial"]

    def test_counts_bug_at_its_severity(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user, severity="critical")
        data = _distributions(admin_client)
        severities = {row["severity"]: row["count"] for row in data["severity"]}
        assert severities["critical"] == 1
        assert severities["major"] == 0

    def test_archived_bug_excluded(
        self, admin_client, organization, project, admin_user, admin_membership, make_bug
    ):
        bug = make_bug(organization, project, admin_user, severity="blocker")
        archive_bug(
            bug=bug, actor=admin_user, membership=admin_membership, expected_version=bug.version
        )
        data = _distributions(admin_client)
        severities = {row["severity"]: row["count"] for row in data["severity"]}
        assert severities["blocker"] == 0
