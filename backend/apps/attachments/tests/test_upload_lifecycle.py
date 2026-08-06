import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.activities.models import ActivityVerb, BugActivity
from apps.attachments.models import Attachment, AttachmentStatus


def _initiate(client, bug, **overrides):
    payload = {
        "original_filename": "notes.txt",
        "content_type": "text/plain",
        "size_bytes": 11,
    }
    payload.update(overrides)
    return client.post(f"/api/bugs/{bug.pk}/attachments/", payload, format="json")


@pytest.mark.django_db
class TestInitiate:
    def test_admin_can_initiate(self, admin_client, bug):
        response = _initiate(admin_client, bug)
        assert response.status_code == 201
        body = response.json()
        assert body["attachment"]["status"] == "pending"
        assert body["upload"]["method"] == "PUT"
        expected_suffix = f"/api/attachments/{body['attachment']['id']}/upload-bytes/"
        assert body["upload"]["url"].endswith(expected_suffix)

    def test_developer_can_initiate(self, developer_client, bug):
        assert _initiate(developer_client, bug).status_code == 201

    def test_qa_can_initiate(self, qa_client, bug):
        assert _initiate(qa_client, bug).status_code == 201

    def test_reporter_can_initiate(self, reporter_client, bug):
        assert _initiate(reporter_client, bug).status_code == 201

    def test_viewer_cannot_initiate(self, viewer_client, bug):
        assert _initiate(viewer_client, bug).status_code == 403

    def test_unsupported_type_rejected(self, admin_client, bug):
        response = _initiate(admin_client, bug, content_type="application/x-executable")
        assert response.status_code == 400
        assert "content_type" in response.json()

    def test_svg_rejected(self, admin_client, bug):
        response = _initiate(admin_client, bug, content_type="image/svg+xml")
        assert response.status_code == 400

    def test_over_size_limit_rejected(self, admin_client, bug):
        response = _initiate(admin_client, bug, size_bytes=10 * 1024 * 1024 + 1)
        assert response.status_code == 400
        assert "size_bytes" in response.json()

    def test_storage_key_is_fully_server_generated(self, admin_client, bug):
        response = _initiate(admin_client, bug, original_filename="../../etc/passwd")
        assert response.status_code == 201
        attachment_id = response.json()["attachment"]["id"]
        attachment = Attachment.objects.get(pk=attachment_id)
        assert attachment.original_filename == "passwd"
        assert "passwd" not in attachment.storage_key
        assert attachment.storage_key == (
            f"attachments/{bug.organization_id}/{bug.id}/{attachment.id}.txt"
        )

    def test_archived_bug_blocks_initiate(self, admin_client, bug):
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version}, format="json")
        assert _initiate(admin_client, bug).status_code == 409

    def test_repeated_initiate_is_throttled(self, admin_client, bug, monkeypatch):
        from django.core.cache import cache
        from rest_framework.throttling import ScopedRateThrottle

        # Same technique as apps.accounts.tests.test_auth's login-throttle
        # test — see that test's comment for why monkeypatch.setitem (not
        # override_settings) is what actually reaches ScopedRateThrottle.
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "attachment-upload", "1/min")
        cache.clear()
        first = _initiate(admin_client, bug, original_filename="one.txt")
        second = _initiate(admin_client, bug, original_filename="two.txt")
        assert first.status_code == 201
        assert second.status_code == 429

    def test_archived_project_blocks_initiate(self, admin_client, bug, project):
        admin_client.post(f"/api/projects/{project.pk}/archive/")
        assert _initiate(admin_client, bug).status_code == 409

    def test_bug_version_unchanged(self, admin_client, bug):
        version_before = bug.version
        _initiate(admin_client, bug)
        bug.refresh_from_db()
        assert bug.version == version_before

    def test_cross_org_bug_returns_404(self, admin_client, other_org_bug):
        assert _initiate(admin_client, other_org_bug).status_code == 404


@pytest.mark.django_db
class TestUploadBytes:
    def test_successful_streamed_upload(
        self, admin_client, bug, make_attachment, admin_user, admin_membership
    ):
        attachment = make_attachment(bug, admin_user, membership=admin_membership)
        upload_file = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")

        response = admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": upload_file},
            format="multipart",
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "uploaded"
        assert body["uploaded_at"] is not None

        attachment.refresh_from_db()
        assert attachment.status == AttachmentStatus.UPLOADED
        assert BugActivity.objects.filter(bug=bug, verb=ActivityVerb.ATTACHMENT_ADDED).count() == 1

    def test_actual_size_mismatch_marks_failed(
        self, admin_client, bug, make_attachment, admin_user, admin_membership
    ):
        attachment = make_attachment(
            bug,
            admin_user,
            membership=admin_membership,
            size_bytes=999,  # declared, but real content differs
        )
        upload_file = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")

        response = admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": upload_file},
            format="multipart",
        )
        assert response.status_code == 409
        attachment.refresh_from_db()
        assert attachment.status == AttachmentStatus.FAILED
        assert attachment.failed_at is not None
        assert not BugActivity.objects.filter(bug=bug, verb=ActivityVerb.ATTACHMENT_ADDED).exists()

    def test_signature_mismatch_marks_failed(
        self, admin_client, bug, make_attachment, admin_user, admin_membership
    ):
        content = b"\x89PNG\r\n\x1a\nnotactuallyapngfile"
        attachment = make_attachment(
            bug,
            admin_user,
            membership=admin_membership,
            content_type="application/pdf",
            size_bytes=len(content),
        )
        upload_file = SimpleUploadedFile("fake.pdf", content, content_type="application/pdf")

        response = admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": upload_file},
            format="multipart",
        )
        assert response.status_code == 409
        attachment.refresh_from_db()
        assert attachment.status == AttachmentStatus.FAILED

    def test_plain_zip_declared_as_docx_marks_failed(
        self, admin_client, bug, make_attachment, admin_user, admin_membership
    ):
        # End-to-end version of apps.attachments.tests.test_validators::
        # TestOOXMLValidation — a plain ZIP shares DOCX's outer PK signature
        # but must still be rejected once the real upload path inspects its
        # actual member structure, not just the magic bytes.
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w") as archive:
            archive.writestr("readme.txt", b"just a plain zip, not a real docx")
        content = buffer.getvalue()

        docx_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        attachment = make_attachment(
            bug,
            admin_user,
            membership=admin_membership,
            content_type=docx_type,
            size_bytes=len(content),
        )
        upload_file = SimpleUploadedFile("fake.docx", content, content_type=docx_type)

        response = admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": upload_file},
            format="multipart",
        )
        assert response.status_code == 409
        attachment.refresh_from_db()
        assert attachment.status == AttachmentStatus.FAILED

    def test_double_upload_returns_409(
        self, admin_client, bug, make_uploaded_attachment, admin_user, admin_membership
    ):
        attachment = make_uploaded_attachment(bug, admin_user, membership=admin_membership)
        upload_file = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")

        response = admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": upload_file},
            format="multipart",
        )
        assert response.status_code == 409

    def test_reupload_to_an_already_failed_attachment_returns_409(
        self, admin_client, bug, make_attachment, admin_user, admin_membership
    ):
        # First attempt fails (declared size doesn't match), leaving the row
        # `failed` — a second attempt, even with genuinely correct bytes,
        # must not be allowed to resurrect that same row. See
        # apps.attachments.services: status transitions are one-way, no
        # retry-on-the-same-row.
        attachment = make_attachment(bug, admin_user, membership=admin_membership, size_bytes=999)
        admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")},
            format="multipart",
        )
        attachment.refresh_from_db()
        assert attachment.status == AttachmentStatus.FAILED

        response = admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": SimpleUploadedFile("notes.txt", b"correct size!", content_type="text/plain")},
            format="multipart",
        )
        assert response.status_code == 409
        attachment.refresh_from_db()
        assert attachment.status == AttachmentStatus.FAILED  # unchanged, not resurrected

    def test_archive_between_initiate_and_upload_blocks_completion(
        self, admin_client, bug, make_attachment, admin_user, admin_membership
    ):
        attachment = make_attachment(bug, admin_user, membership=admin_membership)
        admin_client.post(f"/api/bugs/{bug.pk}/archive/", {"version": bug.version}, format="json")

        upload_file = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")
        response = admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": upload_file},
            format="multipart",
        )
        assert response.status_code == 409
        attachment.refresh_from_db()
        assert attachment.status == AttachmentStatus.PENDING  # untouched — never flipped to failed

    def test_archive_of_project_between_initiate_and_upload_blocks_completion(
        self, admin_client, bug, project, make_attachment, admin_user, admin_membership
    ):
        attachment = make_attachment(bug, admin_user, membership=admin_membership)
        admin_client.post(f"/api/projects/{project.pk}/archive/")

        upload_file = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")
        response = admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": upload_file},
            format="multipart",
        )
        assert response.status_code == 409

    def test_no_partial_file_at_final_path_on_write_failure(
        self, admin_client, bug, make_attachment, admin_user, admin_membership, monkeypatch
    ):
        from apps.attachments import services as attachments_services

        attachment = make_attachment(bug, admin_user, membership=admin_membership)

        class _BoomProvider:
            def save_stream(self, key, chunks):
                for _ in chunks:
                    pass
                raise OSError("simulated disk failure")

        monkeypatch.setattr(attachments_services, "get_storage_provider", lambda: _BoomProvider())
        upload_file = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")

        with pytest.raises(OSError):
            attachments_services.receive_local_upload(
                attachment=attachment, actor=admin_user, uploaded_file=upload_file
            )
        attachment.refresh_from_db()
        # The write itself raised before any status-flip transaction ran, so
        # the row is untouched — still pending, not failed and not uploaded.
        assert attachment.status == AttachmentStatus.PENDING

    def test_bug_version_unchanged_after_upload(
        self, admin_client, bug, make_attachment, admin_user, admin_membership
    ):
        attachment = make_attachment(bug, admin_user, membership=admin_membership)
        version_before = bug.version
        upload_file = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")
        admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": upload_file},
            format="multipart",
        )
        bug.refresh_from_db()
        assert bug.version == version_before

    def test_no_file_submitted_returns_400(
        self, admin_client, bug, make_attachment, admin_user, admin_membership
    ):
        attachment = make_attachment(bug, admin_user, membership=admin_membership)
        response = admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/", {}, format="multipart"
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestUploadBytesPermissions:
    def test_only_uploader_may_send_bytes(
        self, developer_client, bug, make_attachment, admin_user, admin_membership
    ):
        # admin_user initiated it — developer must not be able to supply bytes
        # for someone else's pending upload.
        attachment = make_attachment(bug, admin_user, membership=admin_membership)
        upload_file = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")
        response = developer_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": upload_file},
            format="multipart",
        )
        assert response.status_code == 403

    def test_administrator_is_not_granted_an_upload_bytes_override(
        self, admin_client, bug, make_attachment, developer_user, developer_membership
    ):
        # No administrator override is implemented for upload-bytes: only the
        # user who initiated the upload may supply its bytes, full stop —
        # unlike removal, there is no moderation concept for "finishing
        # someone else's in-flight upload".
        attachment = make_attachment(bug, developer_user, membership=developer_membership)
        upload_file = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")
        response = admin_client.put(
            f"/api/attachments/{attachment.pk}/upload-bytes/",
            {"file": upload_file},
            format="multipart",
        )
        assert response.status_code == 403

    def test_cross_org_upload_bytes_returns_404(self, admin_client, other_org_attachment):
        upload_file = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")
        response = admin_client.put(
            f"/api/attachments/{other_org_attachment.pk}/upload-bytes/",
            {"file": upload_file},
            format="multipart",
        )
        assert response.status_code == 404
