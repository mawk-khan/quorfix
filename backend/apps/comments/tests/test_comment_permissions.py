import pytest

from apps.bugs.models import Bug
from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
from apps.projects.models import Project, ProjectStatus


@pytest.mark.django_db
class TestCommentCreatePermissions:
    def test_administrator_can_comment(self, admin_client, bug):
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/comments/", {"body": "Looking into this."}, format="json"
        )
        assert response.status_code == 201
        assert response.json()["body"] == "Looking into this."

    def test_developer_can_comment(self, developer_client, bug):
        response = developer_client.post(
            f"/api/bugs/{bug.pk}/comments/", {"body": "On it."}, format="json"
        )
        assert response.status_code == 201

    def test_qa_can_comment(self, qa_client, bug):
        response = qa_client.post(
            f"/api/bugs/{bug.pk}/comments/", {"body": "Verified."}, format="json"
        )
        assert response.status_code == 201

    def test_reporter_can_comment(self, reporter_client, bug):
        response = reporter_client.post(
            f"/api/bugs/{bug.pk}/comments/", {"body": "Any update?"}, format="json"
        )
        assert response.status_code == 201

    def test_viewer_cannot_comment(self, viewer_client, bug):
        response = viewer_client.post(
            f"/api/bugs/{bug.pk}/comments/", {"body": "Just watching."}, format="json"
        )
        assert response.status_code == 403

    def test_reporter_can_comment_on_bug_they_did_not_report(
        self, reporter_client, reporter_user, bug
    ):
        # `bug` (from conftest) is reported by admin_user, not reporter_user —
        # comment authorship is not restricted to bugs a reporter filed
        # themselves.
        assert bug.reporter_id != reporter_user.pk
        response = reporter_client.post(
            f"/api/bugs/{bug.pk}/comments/", {"body": "Not mine, still commenting."}, format="json"
        )
        assert response.status_code == 201

    def test_unauthenticated_request_forbidden(self, api_client, bug):
        response = api_client.post(f"/api/bugs/{bug.pk}/comments/", {"body": "Nope"}, format="json")
        assert response.status_code == 403


@pytest.mark.django_db
class TestCommentTenantIsolation:
    @pytest.fixture
    def other_org_bug(self):
        org = Organization.objects.create(name="Other Co", slug="other-co-comments")
        project = Project.objects.create(
            organization=org, key="OTH", name="Other", status=ProjectStatus.ACTIVE
        )
        from django.contrib.auth import get_user_model

        other_user = get_user_model().objects.create_user(
            username="other-org-admin-comments",
            email="other-org-admin-comments@example.com",
            password="x",
        )
        OrganizationMembership.objects.create(
            organization=org, user=other_user, role=CommunityRole.ADMINISTRATOR
        )
        return Bug.objects.create(
            organization=org,
            project=project,
            number=1,
            key="OTH-1",
            title="Other org's bug",
            reporter=other_user,
        )

    def test_cross_org_bug_returns_404_on_list(self, admin_client, other_org_bug):
        response = admin_client.get(f"/api/bugs/{other_org_bug.pk}/comments/")
        assert response.status_code == 404

    def test_cross_org_bug_returns_404_on_create(self, admin_client, other_org_bug):
        response = admin_client.post(
            f"/api/bugs/{other_org_bug.pk}/comments/",
            {"body": "Reaching across orgs"},
            format="json",
        )
        assert response.status_code == 404

    def test_cross_org_comment_id_returns_404(self, admin_client, bug, comment, other_org_bug):
        # A real comment id, but requested under a bug from a different org's
        # detail path — the bug lookup itself is org-scoped, so this must 404
        # before the comment id is even considered.
        response = admin_client.patch(
            f"/api/bugs/{other_org_bug.pk}/comments/{comment.pk}/", {"body": "x"}, format="json"
        )
        assert response.status_code == 404
