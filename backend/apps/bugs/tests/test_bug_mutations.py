import pytest


@pytest.mark.django_db
class TestCreate:
    def test_admin_can_create(self, admin_client, project):
        response = admin_client.post(
            "/api/bugs/", {"project": str(project.pk), "title": "New bug"}, format="json"
        )
        assert response.status_code == 201
        body = response.json()
        assert body["key"] == f"{project.key}-1"
        assert body["status"] == "new"
        assert body["reporter"]["id"]

    def test_reporter_can_create(self, reporter_client, project):
        response = reporter_client.post(
            "/api/bugs/", {"project": str(project.pk), "title": "Reporter bug"}, format="json"
        )
        assert response.status_code == 201

    def test_viewer_cannot_create(self, viewer_client, project):
        response = viewer_client.post(
            "/api/bugs/", {"project": str(project.pk), "title": "Nope"}, format="json"
        )
        assert response.status_code == 403

    def test_blank_title_rejected(self, admin_client, project):
        response = admin_client.post(
            "/api/bugs/", {"project": str(project.pk), "title": "   "}, format="json"
        )
        assert response.status_code == 400
        assert "title" in response.json()

    def test_cross_org_project_returns_structured_400(self, admin_client):
        from apps.organizations.models import Organization
        from apps.projects.models import Project, ProjectStatus

        other_org = Organization.objects.create(name="Other Co", slug="other-co-create")
        other_project = Project.objects.create(
            organization=other_org, key="OTH", name="Other", status=ProjectStatus.ACTIVE
        )
        response = admin_client.post(
            "/api/bugs/", {"project": str(other_project.pk), "title": "Cross org"}, format="json"
        )
        assert response.status_code == 400
        assert "project" in response.json()

    def test_archived_project_returns_409(self, admin_client, project):
        admin_client.post(f"/api/projects/{project.pk}/archive/")
        response = admin_client.post(
            "/api/bugs/", {"project": str(project.pk), "title": "Too late"}, format="json"
        )
        assert response.status_code == 409


@pytest.mark.django_db
class TestUpdate:
    def test_admin_can_update(self, admin_client, bug):
        response = admin_client.patch(
            f"/api/bugs/{bug.pk}/", {"version": bug.version, "title": "Updated"}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated"

    def test_version_conflict_returns_409_with_code_and_current_bug(self, admin_client, bug):
        response = admin_client.patch(
            f"/api/bugs/{bug.pk}/", {"version": bug.version + 1, "title": "x"}, format="json"
        )
        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "bug_version_conflict"
        assert body["bug"]["key"] == bug.key
        assert body["bug"]["version"] == bug.version

    def test_cannot_patch_status_field_at_all(self, admin_client, bug):
        response = admin_client.patch(
            f"/api/bugs/{bug.pk}/", {"version": bug.version, "status": "closed"}, format="json"
        )
        # `status` isn't a field on BugUpdateSerializer, so DRF silently
        # ignores unknown keys — the assertion that matters is that status
        # did NOT change.
        assert response.status_code == 200
        bug.refresh_from_db()
        assert bug.status == "new"

    def test_reporter_cannot_set_priority(
        self, reporter_client, organization, project, reporter_user, reporter_membership, make_bug
    ):
        own_bug = make_bug(organization, project, reporter_user, membership=reporter_membership)
        response = reporter_client.patch(
            f"/api/bugs/{own_bug.pk}/",
            {"version": own_bug.version, "priority": "urgent"},
            format="json",
        )
        assert response.status_code == 403

    def test_viewer_cannot_update(self, viewer_client, bug):
        response = viewer_client.patch(
            f"/api/bugs/{bug.pk}/", {"version": bug.version, "title": "x"}, format="json"
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestTransitionEndpoint:
    def test_admin_can_transition(self, admin_client, bug):
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/transition/",
            {"status": "triaged", "version": bug.version},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["status"] == "triaged"

    def test_invalid_transition_returns_400(self, admin_client, bug):
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/transition/",
            {"status": "closed", "version": bug.version},
            format="json",
        )
        assert response.status_code == 400

    def test_reporter_can_only_reopen(
        self,
        reporter_client,
        admin_client,
        organization,
        project,
        reporter_user,
        reporter_membership,
        make_bug,
    ):
        own_bug = make_bug(organization, project, reporter_user, membership=reporter_membership)
        response = reporter_client.post(
            f"/api/bugs/{own_bug.pk}/transition/",
            {"status": "triaged", "version": own_bug.version},
            format="json",
        )
        assert response.status_code == 403

    def test_viewer_cannot_transition(self, viewer_client, bug):
        response = viewer_client.post(
            f"/api/bugs/{bug.pk}/transition/",
            {"status": "triaged", "version": bug.version},
            format="json",
        )
        assert response.status_code == 403

    def test_available_transitions_reflect_role(
        self,
        admin_client,
        reporter_client,
        organization,
        project,
        admin_user,
        admin_membership,
        reporter_user,
        reporter_membership,
        make_bug,
    ):
        own_bug = make_bug(organization, project, reporter_user, membership=reporter_membership)
        response = reporter_client.get(f"/api/bugs/{own_bug.pk}/")
        assert response.json()["available_transitions"] == []  # new bug isn't reopen-eligible

        response = admin_client.get(f"/api/bugs/{own_bug.pk}/")
        assert "triaged" in response.json()["available_transitions"]


@pytest.mark.django_db
class TestAssignEndpoint:
    def test_admin_can_assign(self, admin_client, bug, developer_user, developer_membership):
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/assign/",
            {"assignee": str(developer_user.pk), "version": bug.version},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["assignee"]["id"] == str(developer_user.pk)

    def test_ineligible_assignee_returns_400(
        self, admin_client, bug, viewer_user, viewer_membership
    ):
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/assign/",
            {"assignee": str(viewer_user.pk), "version": bug.version},
            format="json",
        )
        assert response.status_code == 400
        assert "assignee" in response.json()

    def test_reporter_cannot_assign(
        self, reporter_client, bug, developer_user, developer_membership
    ):
        response = reporter_client.post(
            f"/api/bugs/{bug.pk}/assign/",
            {"assignee": str(developer_user.pk), "version": bug.version},
            format="json",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestArchiveRestoreEndpoints:
    def test_admin_archive_and_restore(self, admin_client, bug):
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/archive/", {"version": bug.version}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["archived_at"] is not None

        response = admin_client.post(
            f"/api/bugs/{bug.pk}/restore/", {"version": response.json()["version"]}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["archived_at"] is None

    def test_non_admin_cannot_archive(self, developer_client, bug):
        response = developer_client.post(
            f"/api/bugs/{bug.pk}/archive/", {"version": bug.version}, format="json"
        )
        assert response.status_code == 403

    def test_double_archive_returns_409(self, admin_client, bug):
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version}, format="json")
        bug.refresh_from_db()
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/archive/", {"version": bug.version}, format="json"
        )
        assert response.status_code == 409


@pytest.mark.django_db
class TestTagEndpoints:
    def test_add_and_remove_tag(self, admin_client, bug):
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/tags/", {"name": "backend", "version": bug.version}, format="json"
        )
        assert response.status_code == 200
        tag_id = response.json()["tags"][0]["id"]

        response = admin_client.delete(
            f"/api/bugs/{bug.pk}/tags/{tag_id}/",
            {"version": response.json()["version"]},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["tags"] == []

    def test_viewer_cannot_add_tag(self, viewer_client, bug):
        response = viewer_client.post(
            f"/api/bugs/{bug.pk}/tags/", {"name": "backend", "version": bug.version}, format="json"
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestWatchEndpoints:
    def test_watch_and_unwatch_do_not_require_version(self, viewer_client, bug):
        response = viewer_client.post(f"/api/bugs/{bug.pk}/watch/")
        assert response.status_code == 200
        assert response.json()["is_watching"] is True

        response = viewer_client.delete(f"/api/bugs/{bug.pk}/watch/")
        assert response.status_code == 200
        assert response.json()["is_watching"] is False

    def test_double_watch_is_ok(self, viewer_client, bug):
        assert viewer_client.post(f"/api/bugs/{bug.pk}/watch/").status_code == 200
        assert viewer_client.post(f"/api/bugs/{bug.pk}/watch/").status_code == 200


@pytest.mark.django_db
class TestRelationshipEndpoints:
    def test_create_and_delete(
        self, admin_client, bug, make_bug, project, organization, admin_user, admin_membership
    ):
        other = make_bug(organization, project, admin_user, membership=admin_membership)
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/relationships/",
            {"related_bug": str(other.pk), "relationship_type": "blocks", "version": bug.version},
            format="json",
        )
        assert response.status_code == 201
        relationship_id = response.json()["relationships"][0]["id"]

        response = admin_client.delete(
            f"/api/bugs/{bug.pk}/relationships/{relationship_id}/",
            {"version": response.json()["version"]},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["relationships"] == []

    def test_reporter_cannot_create_relationship(
        self, reporter_client, bug, make_bug, project, organization, admin_user, admin_membership
    ):
        other = make_bug(organization, project, admin_user, membership=admin_membership)
        response = reporter_client.post(
            f"/api/bugs/{bug.pk}/relationships/",
            {"related_bug": str(other.pk), "relationship_type": "blocks", "version": bug.version},
            format="json",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestCrossOrgObjectReferencesReturn404OrStructured400:
    def test_bug_in_url_from_other_org_returns_404(self, admin_client, admin_user):
        from apps.bugs.models import Bug
        from apps.organizations.models import Organization
        from apps.projects.models import Project, ProjectStatus

        other_org = Organization.objects.create(name="Other Co", slug="other-co-404")
        other_project = Project.objects.create(
            organization=other_org, key="OTH", name="Other", status=ProjectStatus.ACTIVE
        )
        other_bug = Bug.objects.create(
            organization=other_org,
            project=other_project,
            number=1,
            key="OTH-1",
            title="Not yours",
            reporter=admin_user,
        )
        response = admin_client.get(f"/api/bugs/{other_bug.pk}/")
        assert response.status_code == 404
