import pytest
from django.urls import reverse

from apps.bugs.services import archive_bug
from apps.projects.services import archive_project

pytestmark = pytest.mark.django_db


def _recent_activity(client, **params):
    response = client.get(reverse("analytics-recent-activity"), params)
    assert response.status_code == 200, response.json()
    return response.json()


class TestBoundedPagination:
    def test_page_size_bounds_the_result_count(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user, title="Bug 1")
        make_bug(organization, project, admin_user, title="Bug 2")
        make_bug(organization, project, admin_user, title="Bug 3")
        data = _recent_activity(admin_client, page_size=2)
        assert len(data["results"]) == 2
        assert data["next"] is not None

    def test_page_size_cannot_exceed_bounded_max(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user)
        response = admin_client.get(reverse("analytics-recent-activity"), {"page_size": 1000})
        assert response.status_code == 200
        # BoundedPageNumberPagination caps at 100 regardless of what's asked.
        assert response.json()["results"] is not None


class TestOrdering:
    def test_most_recent_activity_first(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user, title="Older bug")
        make_bug(organization, project, admin_user, title="Newer bug")
        data = _recent_activity(admin_client, page_size=10)
        titles = [row["bug"]["title"] for row in data["results"]]
        assert titles[0] == "Newer bug"
        assert titles[-1] == "Older bug"


class TestProjectFiltering:
    def test_project_filter_scopes_to_that_projects_bugs(
        self, admin_client, organization, project, make_project, admin_user, make_bug
    ):
        other = make_project(organization, key="OTH5", name="Other")
        make_bug(organization, project, admin_user, title="In project")
        make_bug(organization, other, admin_user, title="In other project")
        data = _recent_activity(admin_client, project=str(project.pk), page_size=10)
        titles = {row["bug"]["title"] for row in data["results"]}
        assert titles == {"In project"}


class TestArchivedExclusion:
    def test_archived_bug_activity_excluded(
        self, admin_client, organization, project, admin_user, admin_membership, make_bug
    ):
        bug = make_bug(organization, project, admin_user, title="Will be archived")
        make_bug(organization, project, admin_user, title="Stays visible")
        archive_bug(
            bug=bug, actor=admin_user, membership=admin_membership, expected_version=bug.version
        )
        data = _recent_activity(admin_client, page_size=10)
        titles = {row["bug"]["title"] for row in data["results"]}
        assert "Will be archived" not in titles
        assert "Stays visible" in titles

    def test_archived_project_activity_excluded(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user, title="In archived project")
        archive_project(project=project)
        data = _recent_activity(admin_client, page_size=10)
        assert data["results"] == []


class TestResponseShape:
    def test_row_contains_expected_fields(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user, title="Some bug")
        data = _recent_activity(admin_client, page_size=10)
        row = data["results"][0]
        assert set(row.keys()) == {
            "id",
            "bug",
            "project",
            "actor",
            "verb",
            "from_value",
            "to_value",
            "created_at",
        }
        assert set(row["bug"].keys()) == {"id", "key", "title"}
        assert set(row["project"].keys()) == {"id", "key", "name"}
        assert row["actor"]["email"] == admin_user.email

    def test_metadata_is_never_exposed(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        make_comment,
    ):
        bug = make_bug(organization, project, admin_user)
        make_comment(bug, admin_user, membership=admin_membership)
        data = _recent_activity(admin_client, page_size=10)
        for row in data["results"]:
            assert "metadata" not in row


class TestNotCached:
    def test_new_activity_is_visible_immediately(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user, title="First")
        first_call = _recent_activity(admin_client, page_size=10)
        assert len(first_call["results"]) == 1

        make_bug(organization, project, admin_user, title="Second")
        second_call = _recent_activity(admin_client, page_size=10)
        assert len(second_call["results"]) == 2


class TestTenantIsolation:
    def test_other_organization_activity_is_invisible(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        make_bug,
        other_organization,
        other_admin_user,
        other_admin_membership,
        other_project,
    ):
        make_bug(organization, project, admin_user, title="Mine")
        make_bug(other_organization, other_project, other_admin_user, title="Not mine")
        data = _recent_activity(admin_client, page_size=10)
        titles = {row["bug"]["title"] for row in data["results"]}
        assert titles == {"Mine"}
