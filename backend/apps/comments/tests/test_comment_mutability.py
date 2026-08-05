import pytest


@pytest.mark.django_db
class TestArchivedBugBlocksComments:
    def test_archived_bug_blocks_comment_creation(self, admin_client, bug):
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version}, format="json")
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/comments/", {"body": "Too late."}, format="json"
        )
        assert response.status_code == 409

    def test_archived_bug_blocks_comment_edit(self, admin_client, bug, comment):
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version})
        response = admin_client.patch(
            f"/api/bugs/{bug.pk}/comments/{comment.pk}/", {"body": "Edited"}, format="json"
        )
        assert response.status_code == 409

    def test_archived_bug_blocks_own_comment_delete_by_author(
        self,
        admin_client,
        bug,
        developer_user,
        developer_membership,
        developer_client,
        make_comment,
    ):
        # Must be a non-administrator author: an administrator is a moderator
        # and stays exempt from this block regardless of authorship — see
        # test_comment_moderation_on_archived_records.py for the moderator
        # (redact/delete-any) side of this same archived state.
        own_comment = make_comment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version})
        response = developer_client.delete(f"/api/bugs/{bug.pk}/comments/{own_comment.pk}/")
        assert response.status_code == 409

    def test_archived_project_blocks_comment_creation(self, admin_client, bug, project):
        admin_client.post(f"/api/projects/{project.pk}/archive/")
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/comments/", {"body": "Project archived."}, format="json"
        )
        assert response.status_code == 409


@pytest.mark.django_db
def test_comment_creation_does_not_change_bug_version(admin_client, bug):
    version_before = bug.version
    admin_client.post(
        f"/api/bugs/{bug.pk}/comments/", {"body": "No version bump here."}, format="json"
    )
    bug.refresh_from_db()
    assert bug.version == version_before


@pytest.mark.django_db
def test_comment_edit_delete_redact_does_not_change_bug_version(admin_client, bug, comment):
    version_before = bug.version

    admin_client.patch(
        f"/api/bugs/{bug.pk}/comments/{comment.pk}/", {"body": "edited"}, format="json"
    )
    bug.refresh_from_db()
    assert bug.version == version_before

    admin_client.post(f"/api/bugs/{bug.pk}/comments/{comment.pk}/redact/")
    bug.refresh_from_db()
    assert bug.version == version_before
