"""Administrator moderation (redact / delete-any) is deliberately exempt from
the archived-bug/archived-project mutability block that every other comment
mutation (create, edit, author-initiated delete) is subject to — see
apps.comments.services.delete_comment and redact_comment. Author-initiated
deletion stays blocked; only the administrator moderation path bypasses it.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.activities.models import ActivityVerb, BugActivity
from apps.bugs.models import Bug
from apps.comments.services import create_comment
from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
from apps.projects.models import Project, ProjectStatus


@pytest.mark.django_db
class TestAdministratorModerationOnArchivedBug:
    def test_administrator_can_redact_on_archived_bug(
        self, admin_client, bug, developer_user, developer_membership, make_comment
    ):
        target = make_comment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version})

        response = admin_client.post(f"/api/bugs/{bug.pk}/comments/{target.pk}/redact/")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "redacted"
        assert body["body"] == ""
        assert body["redacted_at"] is not None
        assert body["deleted_at"] is None
        assert BugActivity.objects.filter(
            bug=bug, verb=ActivityVerb.COMMENT_REDACTED, metadata__comment_id=str(target.pk)
        ).exists()

    def test_administrator_can_delete_on_archived_bug(
        self, admin_client, bug, developer_user, developer_membership, make_comment
    ):
        target = make_comment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version})

        response = admin_client.delete(f"/api/bugs/{bug.pk}/comments/{target.pk}/")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "deleted"
        assert body["body"] == ""
        assert body["deleted_at"] is not None
        assert body["redacted_at"] is None
        assert BugActivity.objects.filter(
            bug=bug, verb=ActivityVerb.COMMENT_DELETED, metadata__comment_id=str(target.pk)
        ).exists()


@pytest.mark.django_db
class TestAdministratorModerationOnArchivedProject:
    def test_administrator_can_redact_when_project_archived(
        self, admin_client, bug, project, developer_user, developer_membership, make_comment
    ):
        target = make_comment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/projects/{project.pk}/archive/")

        response = admin_client.post(f"/api/bugs/{bug.pk}/comments/{target.pk}/redact/")

        assert response.status_code == 200
        assert response.json()["status"] == "redacted"

    def test_administrator_can_delete_when_project_archived(
        self, admin_client, bug, project, developer_user, developer_membership, make_comment
    ):
        target = make_comment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/projects/{project.pk}/archive/")

        response = admin_client.delete(f"/api/bugs/{bug.pk}/comments/{target.pk}/")

        assert response.status_code == 200
        assert response.json()["status"] == "deleted"


@pytest.mark.django_db
class TestNonAdministratorStaysBlockedOnArchivedRecords:
    def test_author_cannot_delete_own_comment_after_bug_archived(
        self,
        admin_client,
        developer_client,
        bug,
        developer_user,
        developer_membership,
        make_comment,
    ):
        own_comment = make_comment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version})

        response = developer_client.delete(f"/api/bugs/{bug.pk}/comments/{own_comment.pk}/")

        assert response.status_code == 409

    def test_author_cannot_delete_own_comment_after_project_archived(
        self,
        admin_client,
        developer_client,
        bug,
        project,
        developer_user,
        developer_membership,
        make_comment,
    ):
        own_comment = make_comment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/projects/{project.pk}/archive/")

        response = developer_client.delete(f"/api/bugs/{bug.pk}/comments/{own_comment.pk}/")

        assert response.status_code == 409

    def test_non_administrator_cannot_redact_on_archived_bug(
        self,
        admin_client,
        developer_client,
        bug,
        developer_user,
        developer_membership,
        make_comment,
    ):
        target = make_comment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version})

        # Non-administrators can never redact, archived or not — permission is
        # checked before any state/mutability concern.
        response = developer_client.post(f"/api/bugs/{bug.pk}/comments/{target.pk}/redact/")

        assert response.status_code == 403

    def test_non_administrator_non_author_cannot_delete_on_archived_bug(
        self, admin_client, qa_client, bug, developer_user, developer_membership, make_comment
    ):
        target = make_comment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version})

        response = qa_client.delete(f"/api/bugs/{bug.pk}/comments/{target.pk}/")

        assert response.status_code == 403


@pytest.mark.django_db
class TestCrossOrgModeration:
    @pytest.fixture
    def other_org_comment(self):
        org = Organization.objects.create(name="Other Co", slug="other-co-moderation")
        project = Project.objects.create(
            organization=org, key="OTH", name="Other", status=ProjectStatus.ACTIVE
        )
        other_admin = get_user_model().objects.create_user(
            username="other-org-admin-moderation",
            email="other-org-admin-moderation@example.com",
            password="x",
        )
        membership = OrganizationMembership.objects.create(
            organization=org, user=other_admin, role=CommunityRole.ADMINISTRATOR
        )
        other_bug = Bug.objects.create(
            organization=org,
            project=project,
            number=1,
            key="OTH-1",
            title="Other org's bug",
            reporter=other_admin,
        )
        comment = create_comment(
            bug=other_bug, author=other_admin, membership=membership, body="Their comment"
        )
        return other_bug, comment

    def test_cross_org_redact_returns_404(self, admin_client, other_org_comment):
        other_bug, other_comment = other_org_comment
        response = admin_client.post(
            f"/api/bugs/{other_bug.pk}/comments/{other_comment.pk}/redact/"
        )
        assert response.status_code == 404

    def test_cross_org_delete_returns_404(self, admin_client, other_org_comment):
        other_bug, other_comment = other_org_comment
        response = admin_client.delete(f"/api/bugs/{other_bug.pk}/comments/{other_comment.pk}/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestRepeatedModerationOnArchivedRecords:
    def test_repeated_redact_returns_409_even_when_archived(
        self, admin_client, bug, developer_user, developer_membership, make_comment
    ):
        target = make_comment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version})
        admin_client.post(f"/api/bugs/{bug.pk}/comments/{target.pk}/redact/")

        response = admin_client.post(f"/api/bugs/{bug.pk}/comments/{target.pk}/redact/")

        assert response.status_code == 409

    def test_repeated_delete_returns_409_even_when_archived(
        self, admin_client, bug, developer_user, developer_membership, make_comment
    ):
        target = make_comment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version})
        admin_client.delete(f"/api/bugs/{bug.pk}/comments/{target.pk}/")

        response = admin_client.delete(f"/api/bugs/{bug.pk}/comments/{target.pk}/")

        assert response.status_code == 409
