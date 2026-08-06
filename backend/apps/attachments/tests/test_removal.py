from unittest.mock import patch

import pytest

from apps.activities.models import ActivityVerb, BugActivity
from apps.attachments.models import Attachment, AttachmentStatus
from apps.core.task_correlation import _CORRELATION_HEADER_KEY


@pytest.mark.django_db
class TestRemoval:
    def test_uploader_removes_own_attachment_while_mutable(
        self, admin_client, bug, make_uploaded_attachment, admin_user, admin_membership
    ):
        attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
        response = admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        assert response.status_code == 200
        body = response.json()
        assert body["removed_at"] is not None
        assert body["status"] == "uploaded"  # removal doesn't change status, only removed_at

        attachment.refresh_from_db()
        assert attachment.removed_at is not None
        assert (
            BugActivity.objects.filter(bug=bug, verb=ActivityVerb.ATTACHMENT_REMOVED).count() == 1
        )

    def test_uploader_blocked_after_bug_archive(
        self,
        admin_client,
        developer_client,
        bug,
        developer_user,
        developer_membership,
        make_uploaded_attachment,
    ):
        attachment = make_uploaded_attachment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version}, format="json")

        response = developer_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        assert response.status_code == 409
        attachment.refresh_from_db()
        assert attachment.removed_at is None

    def test_uploader_blocked_after_project_archive(
        self,
        admin_client,
        developer_client,
        bug,
        project,
        developer_user,
        developer_membership,
        make_uploaded_attachment,
    ):
        attachment = make_uploaded_attachment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/projects/{project.pk}/archive/")

        response = developer_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        assert response.status_code == 409

    def test_administrator_removes_after_bug_archive(
        self,
        admin_client,
        bug,
        developer_user,
        developer_membership,
        make_uploaded_attachment,
    ):
        attachment = make_uploaded_attachment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version}, format="json")

        response = admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        assert response.status_code == 200
        assert (
            BugActivity.objects.filter(bug=bug, verb=ActivityVerb.ATTACHMENT_REMOVED).count() == 1
        )

    def test_administrator_removes_after_project_archive(
        self,
        admin_client,
        bug,
        project,
        developer_user,
        developer_membership,
        make_uploaded_attachment,
    ):
        attachment = make_uploaded_attachment(bug, developer_user, membership=developer_membership)
        admin_client.post(f"/api/projects/{project.pk}/archive/")

        response = admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        assert response.status_code == 200

    def test_non_uploader_non_admin_denied(
        self, qa_client, bug, make_uploaded_attachment, developer_user, developer_membership
    ):
        attachment = make_uploaded_attachment(bug, developer_user, membership=developer_membership)
        response = qa_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        assert response.status_code == 403

    def test_viewer_cannot_remove(
        self, viewer_client, bug, make_uploaded_attachment, admin_user, admin_membership
    ):
        attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
        response = viewer_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        assert response.status_code == 403

    def test_repeated_removal_returns_409(
        self, admin_client, bug, make_uploaded_attachment, admin_user, admin_membership
    ):
        attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
        admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        response = admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        assert response.status_code == 409

    def test_removing_pending_attachment_returns_409(
        self, admin_client, bug, make_attachment, admin_user, admin_membership
    ):
        attachment = make_attachment(bug, admin_user, membership=admin_membership)
        response = admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        assert response.status_code == 409

    def test_bug_version_unchanged(
        self, admin_client, bug, make_uploaded_attachment, admin_user, admin_membership
    ):
        attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
        version_before = bug.version
        admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        bug.refresh_from_db()
        assert bug.version == version_before

    def test_cross_org_removal_returns_404(self, admin_client, other_org_bug, other_org_attachment):
        response = admin_client.delete(
            f"/api/bugs/{other_org_bug.pk}/attachments/{other_org_attachment.pk}/"
        )
        assert response.status_code == 404


class TestCleanupDispatch:
    @pytest.mark.django_db(transaction=True)
    def test_cleanup_task_is_dispatched_on_removal(
        self, admin_client, bug, make_uploaded_attachment, admin_user, admin_membership
    ):
        # transaction=True: transaction.on_commit callbacks are only ever
        # invoked on a transaction that genuinely commits — the default
        # django_db fixture wraps each test in a transaction that's rolled
        # back, so remove_attachment's on_commit dispatch would silently
        # never fire under it.
        attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
        storage_key = attachment.storage_key

        with patch("apps.attachments.tasks.delete_attachment_object.apply_async") as mock_delay:
            response = admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        assert response.status_code == 200
        mock_delay.assert_called_once()
        assert mock_delay.call_args.kwargs["args"] == [storage_key]
        # A real HTTP request always has a request ID (see
        # apps.core.middleware.request_id) — the dispatch propagates it as a
        # task header rather than a fixed/empty value.
        assert mock_delay.call_args.kwargs["headers"][_CORRELATION_HEADER_KEY]

    @pytest.mark.django_db
    def test_cleanup_task_deletes_the_object_and_is_idempotent(
        self, bug, make_uploaded_attachment, admin_user, admin_membership
    ):
        from apps.attachments.providers import get_storage_provider
        from apps.attachments.tasks import delete_attachment_object

        attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
        provider = get_storage_provider()
        assert provider.resolve_download(attachment.storage_key) is not None

        delete_attachment_object.apply(args=[attachment.storage_key])
        assert provider.resolve_download(attachment.storage_key) is None

        # Calling it again against an already-gone key must not raise.
        delete_attachment_object.apply(args=[attachment.storage_key])

    @pytest.mark.django_db(transaction=True)
    def test_broker_failure_does_not_roll_back_the_db_removal(
        self, admin_client, bug, make_uploaded_attachment, admin_user, admin_membership
    ):
        attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)

        with patch(
            "apps.attachments.tasks.delete_attachment_object.apply_async",
            side_effect=ConnectionError("broker unreachable"),
        ):
            response = admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")

        # The removal itself must succeed regardless of the dispatch failure.
        assert response.status_code == 200
        attachment.refresh_from_db()
        assert attachment.removed_at is not None

    def test_exhausted_retries_are_logged(self, caplog):
        import logging

        from apps.attachments.tasks import delete_attachment_object

        def _raise_exhausted(*args, **kwargs):
            raise delete_attachment_object.MaxRetriesExceededError()

        with (
            patch(
                "apps.attachments.tasks.get_storage_provider",
                side_effect=OSError("simulated persistent failure"),
            ),
            patch.object(delete_attachment_object, "retry", side_effect=_raise_exhausted),
            caplog.at_level(logging.ERROR),
        ):
            delete_attachment_object.apply(args=["attachments/some/orphaned/key.txt"])

        assert any("permanently failed" in record.message for record in caplog.records)


@pytest.mark.django_db
def test_attachment_row_persists_after_removal_for_the_activity_trail(
    admin_client, bug, make_uploaded_attachment, admin_user, admin_membership
):
    attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
    admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
    assert Attachment.objects.filter(pk=attachment.pk, status=AttachmentStatus.UPLOADED).exists()
