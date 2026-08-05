import pytest

from apps.projects.models import Project

NON_ADMIN_ROLE_FIXTURES = ["developer_user", "qa_user", "reporter_user", "viewer_user"]
NON_ADMIN_MEMBERSHIP_FIXTURES = [
    "developer_membership",
    "qa_membership",
    "reporter_membership",
    "viewer_membership",
]


@pytest.mark.django_db
class TestProjectCreate:
    @pytest.mark.parametrize(
        "user_fixture,membership_fixture",
        zip(NON_ADMIN_ROLE_FIXTURES, NON_ADMIN_MEMBERSHIP_FIXTURES, strict=True),
    )
    def test_non_administrator_cannot_create(
        self, api_client, request, user_fixture, membership_fixture
    ):
        user = request.getfixturevalue(user_fixture)
        request.getfixturevalue(membership_fixture)
        api_client.force_login(user)

        response = api_client.post("/api/projects/", {"name": "Engine", "key": "ENG"})
        assert response.status_code == 403

    def test_administrator_can_create(self, admin_client, organization):
        response = admin_client.post("/api/projects/", {"name": "Engine", "key": "ENG"})
        assert response.status_code == 201
        body = response.json()
        assert body["key"] == "ENG"
        assert body["status"] == "active"
        assert Project.objects.filter(organization=organization, key="ENG").exists()

    def test_key_is_normalized_to_uppercase_and_trimmed(self, admin_client):
        response = admin_client.post("/api/projects/", {"name": "Engine", "key": "  eng  "})
        assert response.status_code == 201
        assert response.json()["key"] == "ENG"

    def test_invalid_key_format_returns_400(self, admin_client):
        response = admin_client.post("/api/projects/", {"name": "Engine", "key": "1E"})
        assert response.status_code == 400
        assert "key" in response.json()

    def test_key_too_short_returns_400(self, admin_client):
        response = admin_client.post("/api/projects/", {"name": "Engine", "key": "E"})
        assert response.status_code == 400
        assert "key" in response.json()

    def test_duplicate_key_pre_check_returns_structured_400(
        self, admin_client, organization, make_project
    ):
        make_project(organization, key="ENG")
        response = admin_client.post("/api/projects/", {"name": "Another Engine", "key": "ENG"})
        assert response.status_code == 400
        assert response.json() == {
            "key": ["A project with this key already exists in this organization."]
        }

    def test_duplicate_key_db_race_returns_the_same_structured_400(
        self, admin_client, organization, make_project, monkeypatch
    ):
        make_project(organization, key="ENG")
        # Force the serializer's pre-check to pass so the request only fails
        # via the DB's unique constraint — the same failure a real race
        # between two concurrent creates would hit.
        monkeypatch.setattr("apps.projects.serializers.project_key_exists", lambda *a, **k: False)

        response = admin_client.post("/api/projects/", {"name": "Another Engine", "key": "ENG"})
        assert response.status_code == 400
        assert response.json() == {
            "key": ["A project with this key already exists in this organization."]
        }

    def test_lead_must_be_a_member_of_the_organization(self, admin_client, make_user):
        outsider = make_user("outsider@example.com")
        response = admin_client.post(
            "/api/projects/", {"name": "Engine", "key": "ENG", "lead": str(outsider.pk)}
        )
        assert response.status_code == 400
        assert "lead" in response.json()

    def test_any_community_role_may_be_lead(
        self, admin_client, organization, viewer_user, viewer_membership
    ):
        response = admin_client.post(
            "/api/projects/", {"name": "Engine", "key": "ENG", "lead": str(viewer_user.pk)}
        )
        assert response.status_code == 201
        assert response.json()["lead"]["id"] == str(viewer_user.pk)

    def test_organization_cannot_be_supplied_by_the_client(
        self, admin_client, organization, make_user
    ):
        from apps.organizations.models import Organization

        other_org = Organization.objects.create(name="Other Co", slug="other-co")
        response = admin_client.post(
            "/api/projects/", {"name": "Engine", "key": "ENG", "organization": str(other_org.pk)}
        )
        assert response.status_code == 201
        project = Project.objects.get(key="ENG")
        assert project.organization_id == organization.pk


@pytest.mark.django_db
class TestProjectUpdate:
    @pytest.mark.parametrize(
        "user_fixture,membership_fixture",
        zip(NON_ADMIN_ROLE_FIXTURES, NON_ADMIN_MEMBERSHIP_FIXTURES, strict=True),
    )
    def test_non_administrator_cannot_update(
        self, api_client, request, project, user_fixture, membership_fixture
    ):
        user = request.getfixturevalue(user_fixture)
        request.getfixturevalue(membership_fixture)
        api_client.force_login(user)

        response = api_client.patch(f"/api/projects/{project.pk}/", {"name": "New name"})
        assert response.status_code == 403

    def test_administrator_can_update_name_and_status(self, admin_client, project):
        response = admin_client.patch(
            f"/api/projects/{project.pk}/", {"name": "Renamed", "status": "on_hold"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"
        assert response.json()["status"] == "on_hold"

    def test_key_is_not_editable(self, admin_client, project):
        original_key = project.key
        response = admin_client.patch(f"/api/projects/{project.pk}/", {"key": "NEWKEY"})
        assert response.status_code == 200
        project.refresh_from_db()
        assert project.key == original_key

    def test_update_rejects_ineligible_lead(self, admin_client, project, make_user):
        outsider = make_user("outsider@example.com")
        response = admin_client.patch(f"/api/projects/{project.pk}/", {"lead": str(outsider.pk)})
        assert response.status_code == 400
        assert "lead" in response.json()

    def test_archived_project_cannot_be_patched(self, admin_client, project):
        admin_client.post(f"/api/projects/{project.pk}/archive/")
        response = admin_client.patch(f"/api/projects/{project.pk}/", {"name": "Renamed"})
        assert response.status_code == 409
        project.refresh_from_db()
        assert project.name != "Renamed"

    def test_archived_project_patch_returns_409_even_with_invalid_payload(
        self, admin_client, project, make_user
    ):
        """409 (archived) must win over 400 (bad payload) — the client
        shouldn't have to guess which error they'll get."""
        admin_client.post(f"/api/projects/{project.pk}/archive/")
        outsider = make_user("outsider@example.com")
        response = admin_client.patch(f"/api/projects/{project.pk}/", {"lead": str(outsider.pk)})
        assert response.status_code == 409


@pytest.mark.django_db
class TestProjectArchiveRestore:
    @pytest.mark.parametrize(
        "user_fixture,membership_fixture",
        zip(NON_ADMIN_ROLE_FIXTURES, NON_ADMIN_MEMBERSHIP_FIXTURES, strict=True),
    )
    def test_non_administrator_cannot_archive(
        self, api_client, request, project, user_fixture, membership_fixture
    ):
        user = request.getfixturevalue(user_fixture)
        request.getfixturevalue(membership_fixture)
        api_client.force_login(user)

        response = api_client.post(f"/api/projects/{project.pk}/archive/")
        assert response.status_code == 403

    def test_administrator_can_archive_and_restore(self, admin_client, project):
        archive_response = admin_client.post(f"/api/projects/{project.pk}/archive/")
        assert archive_response.status_code == 200
        assert archive_response.json()["archived_at"] is not None

        restore_response = admin_client.post(f"/api/projects/{project.pk}/restore/")
        assert restore_response.status_code == 200
        assert restore_response.json()["archived_at"] is None

    def test_archiving_twice_returns_409(self, admin_client, project):
        admin_client.post(f"/api/projects/{project.pk}/archive/")
        response = admin_client.post(f"/api/projects/{project.pk}/archive/")
        assert response.status_code == 409

    def test_restoring_a_non_archived_project_returns_409(self, admin_client, project):
        response = admin_client.post(f"/api/projects/{project.pk}/restore/")
        assert response.status_code == 409

    def test_archived_project_is_still_readable(
        self, api_client, organization, viewer_user, viewer_membership, admin_client, project
    ):
        admin_client.post(f"/api/projects/{project.pk}/archive/")
        api_client.force_login(viewer_user)
        response = api_client.get(f"/api/projects/{project.pk}/")
        assert response.status_code == 200
        assert response.json()["archived_at"] is not None
