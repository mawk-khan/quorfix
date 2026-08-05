import pytest
from django.urls import reverse

from apps.bugs.models import BugStatus
from apps.bugs.services import archive_bug, transition_bug
from apps.projects.services import archive_project

pytestmark = pytest.mark.django_db


def _active_projects(client, **params):
    response = client.get(reverse("analytics-active-projects"), params)
    assert response.status_code == 200, response.json()
    return {row["key"]: row for row in response.json()}


class TestActiveProjects:
    def test_non_archived_project_is_included(self, admin_client, project):
        data = _active_projects(admin_client)
        assert project.key in data

    def test_archived_project_is_excluded(self, admin_client, project):
        archive_project(project=project)
        data = _active_projects(admin_client)
        assert project.key not in data

    def test_totals_reflect_current_bug_counts(
        self, admin_client, organization, project, admin_user, admin_membership, make_bug
    ):
        make_bug(organization, project, admin_user, title="Bug 1")
        bug2 = make_bug(organization, project, admin_user, title="Bug 2")
        transition_bug(
            bug=bug2,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.TRIAGED,
            expected_version=bug2.version,
        )
        data = _active_projects(admin_client)
        assert data[project.key]["total_bugs"] == 2
        assert data[project.key]["open_bugs"] == 2

    def test_archived_bug_excluded_from_both_totals(
        self, admin_client, organization, project, admin_user, admin_membership, make_bug
    ):
        bug = make_bug(organization, project, admin_user)
        archive_bug(
            bug=bug, actor=admin_user, membership=admin_membership, expected_version=bug.version
        )
        data = _active_projects(admin_client)
        assert data[project.key]["total_bugs"] == 0
        assert data[project.key]["open_bugs"] == 0

    def test_terminal_status_bug_counts_toward_total_but_not_open(
        self, admin_client, organization, project, admin_user, admin_membership, make_bug
    ):
        bug = make_bug(organization, project, admin_user)
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.WONT_FIX,
            expected_version=bug.version,
        )
        data = _active_projects(admin_client)
        assert data[project.key]["total_bugs"] == 1
        assert data[project.key]["open_bugs"] == 0

    def test_response_includes_expected_fields(self, admin_client, project):
        data = _active_projects(admin_client)
        row = data[project.key]
        assert set(row.keys()) == {"id", "key", "name", "status", "total_bugs", "open_bugs"}

    def test_project_query_param_is_ignored_not_an_error(
        self, admin_client, organization, project, make_project, admin_user, make_bug
    ):
        other = make_project(organization, key="OTH6", name="Other")
        make_bug(organization, project, admin_user)
        make_bug(organization, other, admin_user)
        # active-projects has no project filter at all — passing one must be
        # harmless and must not narrow the result to a single project.
        response = admin_client.get(
            reverse("analytics-active-projects"), {"project": str(project.pk)}
        )
        assert response.status_code == 200
        keys = {row["key"] for row in response.json()}
        assert keys == {project.key, other.key}

    def test_multiple_active_projects_all_returned(
        self, admin_client, organization, project, make_project
    ):
        other = make_project(organization, key="OTH7", name="Other")
        data = _active_projects(admin_client)
        assert {project.key, other.key} <= set(data.keys())


class TestActiveProjectsTenantIsolation:
    def test_other_organization_projects_invisible(
        self, admin_client, project, other_organization, other_project
    ):
        data = _active_projects(admin_client)
        assert other_project.key not in data
