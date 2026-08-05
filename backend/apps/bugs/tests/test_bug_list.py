import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext


@pytest.mark.django_db
class TestBugList:
    def test_requires_authentication(self, api_client):
        response = api_client.get("/api/bugs/")
        assert response.status_code == 403

    def test_any_member_can_list(self, viewer_client, bug):
        response = viewer_client.get("/api/bugs/")
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"count", "next", "previous", "results"}
        assert body["results"][0]["key"] == bug.key

    def test_default_excludes_archived(self, admin_client, bug):
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version}, format="json")
        response = admin_client.get("/api/bugs/")
        assert response.json()["count"] == 0

    def test_archived_true_returns_only_archived(
        self, admin_client, bug, make_bug, organization, project, admin_user, admin_membership
    ):
        other = make_bug(organization, project, admin_user, membership=admin_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version}, format="json")
        response = admin_client.get("/api/bugs/?archived=true")
        keys = {b["key"] for b in response.json()["results"]}
        assert keys == {bug.key}
        assert other.key not in keys

    def test_filter_by_status(self, admin_client, bug):
        admin_client.post(
            f"/api/bugs/{bug.pk}/transition/",
            {"status": "triaged", "version": bug.version},
            format="json",
        )
        response = admin_client.get("/api/bugs/?status=triaged")
        assert response.json()["count"] == 1
        response = admin_client.get("/api/bugs/?status=new")
        assert response.json()["count"] == 0

    def test_filter_by_multiple_statuses(
        self, admin_client, bug, make_bug, organization, project, admin_user, admin_membership
    ):
        make_bug(organization, project, admin_user, membership=admin_membership)
        response = admin_client.get("/api/bugs/?status=new,triaged")
        assert response.json()["count"] == 2

    def test_invalid_status_returns_400(self, admin_client):
        response = admin_client.get("/api/bugs/?status=not-a-status")
        assert response.status_code == 400
        assert "status" in response.json()

    def test_filter_by_project(
        self, admin_client, bug, make_bug, organization, make_project, admin_user, admin_membership
    ):
        other_project = make_project(organization, key="OTP", name="Other project")
        make_bug(organization, other_project, admin_user, membership=admin_membership)
        response = admin_client.get(f"/api/bugs/?project={bug.project_id}")
        assert response.json()["count"] == 1
        assert response.json()["results"][0]["key"] == bug.key

    def test_search_matches_key_or_title(self, admin_client, bug):
        response = admin_client.get(f"/api/bugs/?search={bug.key}")
        assert response.json()["count"] == 1
        response = admin_client.get("/api/bugs/?search=nonexistent-xyz")
        assert response.json()["count"] == 0

    def test_unassigned_filter(self, admin_client, bug, developer_user, developer_membership):
        response = admin_client.get("/api/bugs/?unassigned=true")
        assert response.json()["count"] == 1
        admin_client.post(
            f"/api/bugs/{bug.pk}/assign/",
            {"assignee": str(developer_user.pk), "version": bug.version},
            format="json",
        )
        response = admin_client.get("/api/bugs/?unassigned=true")
        assert response.json()["count"] == 0

    def test_invalid_ordering_field_returns_400(self, admin_client):
        response = admin_client.get("/api/bugs/?ordering=not_a_field")
        assert response.status_code == 400
        assert "ordering" in response.json()

    def test_invalid_uuid_filter_returns_400(self, admin_client):
        response = admin_client.get("/api/bugs/?project=not-a-uuid")
        assert response.status_code == 400

    def test_priority_ordering_is_business_not_alphabetical(
        self, admin_client, organization, project, admin_user, admin_membership, make_bug
    ):
        low = make_bug(
            organization,
            project,
            admin_user,
            membership=admin_membership,
            priority="low",
            title="Low",
        )
        urgent = make_bug(
            organization,
            project,
            admin_user,
            membership=admin_membership,
            priority="urgent",
            title="Urgent",
        )
        medium = make_bug(
            organization,
            project,
            admin_user,
            membership=admin_membership,
            priority="medium",
            title="Medium",
        )

        response = admin_client.get("/api/bugs/?ordering=-priority")
        keys_in_order = [b["key"] for b in response.json()["results"]]
        assert (
            keys_in_order.index(urgent.key)
            < keys_in_order.index(medium.key)
            < keys_in_order.index(low.key)
        )

    def test_tenant_isolation(self, admin_client, bug):
        from apps.bugs.models import Bug
        from apps.organizations.models import Organization
        from apps.projects.models import Project, ProjectStatus

        other_org = Organization.objects.create(name="Other Co", slug="other-co-list")
        other_project = Project.objects.create(
            organization=other_org, key="OTH", name="Other", status=ProjectStatus.ACTIVE
        )
        Bug.objects.create(
            organization=other_org,
            project=other_project,
            number=1,
            key="OTH-1",
            title="Should not appear",
            reporter=bug.reporter,
        )
        response = admin_client.get("/api/bugs/")
        assert response.json()["count"] == 1
        assert response.json()["results"][0]["key"] == bug.key


@pytest.mark.django_db
def test_list_query_count_does_not_grow_with_bug_count(
    admin_client,
    organization,
    project,
    admin_user,
    admin_membership,
    make_bug,
    developer_user,
    developer_membership,
):
    def _query_count():
        with CaptureQueriesContext(connection) as ctx:
            response = admin_client.get("/api/bugs/")
        assert response.status_code == 200
        return len(ctx.captured_queries)

    make_bug(organization, project, admin_user, membership=admin_membership)
    small_count = _query_count()

    for i in range(10):
        b = make_bug(
            organization, project, admin_user, membership=admin_membership, title=f"Bug {i}"
        )
        from apps.bugs.services import assign_bug

        assign_bug(
            bug=b,
            actor=admin_user,
            membership=admin_membership,
            assignee_id=str(developer_user.pk),
            expected_version=b.version,
        )
    large_count = _query_count()

    assert small_count == large_count


@pytest.mark.django_db
def test_detail_query_count_is_bounded(admin_client, bug):
    with CaptureQueriesContext(connection) as ctx:
        response = admin_client.get(f"/api/bugs/{bug.pk}/")
    assert response.status_code == 200
    # A handful of queries (bug+joins, relationships, watcher count) — not
    # proportional to anything that grows with dataset size.
    assert len(ctx.captured_queries) < 10
