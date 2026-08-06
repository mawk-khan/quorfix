import logging

import pytest

from apps.attachments.models import AttachmentStatus


@pytest.mark.django_db
class TestDownloadAuthorization:
    def test_uploaded_attachment_downloads(
        self, admin_client, bug, make_uploaded_attachment, admin_user, admin_membership
    ):
        attachment = make_uploaded_attachment(
            bug, admin_user, membership=admin_membership, content=b"hello world"
        )
        response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/download/")
        assert response.status_code == 200
        assert b"".join(response.streaming_content) == b"hello world"

    def test_any_org_member_can_download(
        self, viewer_client, bug, make_uploaded_attachment, admin_user, admin_membership
    ):
        # Read is open to every org member, including Viewer — only upload
        # and remove are role-gated.
        attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
        response = viewer_client.get(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/download/")
        assert response.status_code == 200

    def test_pending_attachment_returns_404(
        self, admin_client, bug, make_attachment, admin_user, admin_membership
    ):
        attachment = make_attachment(bug, admin_user, membership=admin_membership)
        response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/download/")
        assert response.status_code == 404

    def test_failed_attachment_returns_404(
        self, admin_client, bug, make_attachment, admin_user, admin_membership
    ):
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Reach `failed` through the real upload path (declared size that
        # doesn't match the actual bytes) rather than poking internal state.
        attachment = make_attachment(bug, admin_user, membership=admin_membership, size_bytes=999)
        upload_file = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")
        admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": upload_file},
            format="multipart",
        )
        response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/download/")
        assert response.status_code == 404

    def test_removed_attachment_returns_404(
        self, admin_client, bug, make_uploaded_attachment, admin_user, admin_membership
    ):
        attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
        admin_client.delete(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/")
        response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/download/")
        assert response.status_code == 404

    def test_cross_org_download_returns_404(
        self, admin_client, other_org_bug, other_org_attachment
    ):
        response = admin_client.get(
            f"/api/bugs/{other_org_bug.pk}/attachments/{other_org_attachment.pk}/download/"
        )
        assert response.status_code == 404

    def test_attachment_from_a_different_bug_returns_404(
        self,
        admin_client,
        bug,
        project,
        organization,
        admin_user,
        admin_membership,
        make_uploaded_attachment,
        make_bug,
    ):
        other_bug = make_bug(organization, project, admin_user, membership=admin_membership)
        attachment = make_uploaded_attachment(other_bug, admin_user, membership=admin_membership)
        # Real attachment, real org — but requested under the wrong bug's URL.
        response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/download/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestDownloadHeaders:
    def test_headers_are_correct(
        self, admin_client, bug, make_uploaded_attachment, admin_user, admin_membership
    ):
        attachment = make_uploaded_attachment(
            bug,
            admin_user,
            membership=admin_membership,
            content=b"content",
            content_type="text/plain",
            original_filename="report.txt",
        )
        response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/download/")
        assert response.status_code == 200
        assert response["Content-Type"] == "text/plain"
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["Cache-Control"] == "private, no-store"
        assert "attachment" in response["Content-Disposition"]
        assert "report.txt" in response["Content-Disposition"]

    def test_filename_with_special_characters_is_escaped_safely(
        self, admin_client, bug, admin_user, admin_membership, make_attachment
    ):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.attachments.services import receive_local_upload

        # sanitize_filename already strips quotes/control characters at
        # initiate time, but the header-building step itself (Django's
        # FileResponse) must never be handed a raw, unescaped string either —
        # this exercises the full path end-to-end.
        attachment = make_attachment(
            bug,
            admin_user,
            membership=admin_membership,
            original_filename='weird"name.txt',
            content_type="text/plain",
            size_bytes=4,
        )
        upload_file = SimpleUploadedFile("weird_name.txt", b"data", content_type="text/plain")
        receive_local_upload(attachment=attachment, actor=admin_user, uploaded_file=upload_file)

        response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/download/")
        assert response.status_code == 200
        # No CR/LF or unescaped quote survives into the header in a way that
        # could break out of the filename="..." quoting or inject a header.
        disposition = response["Content-Disposition"]
        assert "\r" not in disposition and "\n" not in disposition
        assert disposition.count('"') == 2  # exactly the opening/closing pair


@pytest.mark.django_db
def test_missing_storage_object_returns_404_and_logs(
    admin_client, bug, make_uploaded_attachment, admin_user, admin_membership, caplog
):
    attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
    # Simulate the file having disappeared out from under a correctly
    # "uploaded" DB row (e.g. manual intervention, disk issue) — the API must
    # not leak a filesystem error.
    from apps.attachments.services import get_storage_provider

    get_storage_provider().delete(attachment.storage_key)

    with caplog.at_level(logging.ERROR):
        response = admin_client.get(f"/api/bugs/{bug.pk}/attachments/{attachment.pk}/download/")
    assert response.status_code == 404
    assert any("missing" in record.message for record in caplog.records)
    assert attachment.status == AttachmentStatus.UPLOADED  # DB row itself is untouched

    # Neither the response body nor the server log may carry the raw storage
    # key or absolute filesystem path (Chunk J §7) — the log line instead
    # carries a non-reversible hash of the key (see
    # apps.attachments.providers.hash_storage_key), present so a specific
    # object's failures can still be correlated across log lines without
    # exposing the org/bug/attachment UUID structure the raw key embeds.
    from django.conf import settings

    from apps.attachments.providers import hash_storage_key

    body = response.content.decode()
    assert settings.ATTACHMENTS_LOCAL_ROOT not in body
    assert str(attachment.storage_key) not in body
    assert not any(str(attachment.storage_key) in record.message for record in caplog.records)
    assert any(
        hash_storage_key(attachment.storage_key) in record.getMessage() for record in caplog.records
    )
    assert "/attachment-storage/" not in body
