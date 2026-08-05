import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.organizations.models import CommunityRole


@pytest.mark.django_db
class TestProjectList:
    def test_requires_authentication(self, api_client):
        response = api_client.get("/api/projects/")
        assert response.status_code == 403

    def test_any_member_can_list(
        self, api_client, organization, viewer_user, viewer_membership, project
    ):
        api_client.force_login(viewer_user)
        response = api_client.get("/api/projects/")
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"count", "next", "previous", "results"}
        assert body["count"] == 1
        assert body["results"][0]["key"] == project.key

    def test_default_list_excludes_archived(self, admin_client, organization, make_project):
        active = make_project(organization, key="ACT", name="Active")
        archived = make_project(organization, key="ARC", name="Archived")
        admin_client.post(f"/api/projects/{archived.pk}/archive/")

        response = admin_client.get("/api/projects/")
        keys = {p["key"] for p in response.json()["results"]}
        assert keys == {active.key}

    def test_archived_true_returns_only_archived(self, admin_client, organization, make_project):
        active = make_project(organization, key="ACT", name="Active")
        archived = make_project(organization, key="ARC", name="Archived")
        admin_client.post(f"/api/projects/{archived.pk}/archive/")

        response = admin_client.get("/api/projects/?archived=true")
        keys = {p["key"] for p in response.json()["results"]}
        assert keys == {archived.key}
        assert active.key not in keys

    def test_archived_all_returns_both(self, admin_client, organization, make_project):
        active = make_project(organization, key="ACT", name="Active")
        archived = make_project(organization, key="ARC", name="Archived")
        admin_client.post(f"/api/projects/{archived.pk}/archive/")

        response = admin_client.get("/api/projects/?archived=all")
        keys = {p["key"] for p in response.json()["results"]}
        assert keys == {active.key, archived.key}

    def test_non_administrator_can_also_use_archived_all(
        self, api_client, organization, viewer_user, viewer_membership, admin_client, make_project
    ):
        active = make_project(organization, key="ACT", name="Active")
        archived = make_project(organization, key="ARC", name="Archived")
        admin_client.post(f"/api/projects/{archived.pk}/archive/")

        api_client.force_login(viewer_user)
        response = api_client.get("/api/projects/?archived=all")
        keys = {p["key"] for p in response.json()["results"]}
        assert keys == {active.key, archived.key}

    def test_invalid_archived_value_returns_structured_400(self, admin_client):
        response = admin_client.get("/api/projects/?archived=bogus")
        assert response.status_code == 400
        assert "archived" in response.json()

    def test_search_matches_name_or_key_case_insensitively(
        self, admin_client, organization, make_project
    ):
        make_project(organization, key="ENG", name="Engine Team")
        make_project(organization, key="MKT", name="Marketing")

        by_name = admin_client.get("/api/projects/?search=engine")
        assert [p["key"] for p in by_name.json()["results"]] == ["ENG"]

        by_key = admin_client.get("/api/projects/?search=mkt")
        assert [p["key"] for p in by_key.json()["results"]] == ["MKT"]

    def test_search_is_trimmed(self, admin_client, organization, make_project):
        make_project(organization, key="ENG", name="Engine Team")
        response = admin_client.get("/api/projects/?search=%20%20ENG%20%20")
        assert [p["key"] for p in response.json()["results"]] == ["ENG"]

    def test_empty_search_behaves_as_no_filter(self, admin_client, organization, make_project):
        make_project(organization, key="ENG", name="Engine Team")
        make_project(organization, key="MKT", name="Marketing")
        response = admin_client.get("/api/projects/?search=")
        assert response.json()["count"] == 2

    def test_search_and_archived_are_org_scoped(self, admin_client, make_project):
        from apps.organizations.models import Organization

        other_org = Organization.objects.create(name="Other Co", slug="other-co")
        make_project(other_org, key="ENG", name="Engine Team")

        response = admin_client.get("/api/projects/?search=engine")
        assert response.json()["count"] == 0


@pytest.mark.django_db
def test_list_projects_query_count_does_not_grow_with_project_count(
    admin_client, organization, make_project, make_user, make_membership
):
    def _query_count():
        with CaptureQueriesContext(connection) as ctx:
            response = admin_client.get("/api/projects/")
        assert response.status_code == 200
        return len(ctx.captured_queries)

    def add_projects(n, offset):
        for i in range(n):
            lead = make_user(f"lead{offset + i}@example.com")
            make_membership(organization, lead, role=CommunityRole.DEVELOPER)
            make_project(
                organization, key=f"P{offset + i}", name=f"Project {offset + i}", lead=lead
            )

    add_projects(1, offset=0)
    small_count = _query_count()

    add_projects(4, offset=1)
    large_count = _query_count()

    assert small_count == large_count
