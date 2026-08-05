import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.attachments.models import Attachment, AttachmentStatus


def _base_kwargs(bug, uploader):
    return dict(
        organization=bug.organization,
        bug=bug,
        uploaded_by=uploader,
        original_filename="notes.txt",
        content_type="text/plain",
        size_bytes=10,
    )


@pytest.mark.django_db
class TestAttachmentStatusConstraint:
    def test_valid_pending(self, bug, admin_user):
        attachment = Attachment.objects.create(
            **_base_kwargs(bug, admin_user), storage_key="attachments/a/b/c.txt"
        )
        assert attachment.status == AttachmentStatus.PENDING
        assert attachment.uploaded_at is None
        assert attachment.failed_at is None
        assert attachment.removed_at is None

    def test_valid_uploaded(self, bug, admin_user):
        attachment = Attachment.objects.create(
            **_base_kwargs(bug, admin_user),
            storage_key="attachments/a/b/c.txt",
            status=AttachmentStatus.UPLOADED,
            uploaded_at=timezone.now(),
        )
        assert attachment.uploaded_at is not None
        assert attachment.failed_at is None

    def test_valid_uploaded_then_removed(self, bug, admin_user):
        attachment = Attachment.objects.create(
            **_base_kwargs(bug, admin_user),
            storage_key="attachments/a/b/c.txt",
            status=AttachmentStatus.UPLOADED,
            uploaded_at=timezone.now(),
            removed_at=timezone.now(),
        )
        assert attachment.removed_at is not None

    def test_valid_failed(self, bug, admin_user):
        attachment = Attachment.objects.create(
            **_base_kwargs(bug, admin_user),
            storage_key="attachments/a/b/c.txt",
            status=AttachmentStatus.FAILED,
            failed_at=timezone.now(),
        )
        assert attachment.failed_at is not None
        assert attachment.uploaded_at is None

    def test_pending_with_uploaded_at_rejected(self, bug, admin_user):
        with pytest.raises(IntegrityError), transaction.atomic():
            Attachment.objects.create(
                **_base_kwargs(bug, admin_user),
                storage_key="attachments/a/b/c.txt",
                status=AttachmentStatus.PENDING,
                uploaded_at=timezone.now(),
            )

    def test_pending_with_removed_at_rejected(self, bug, admin_user):
        with pytest.raises(IntegrityError), transaction.atomic():
            Attachment.objects.create(
                **_base_kwargs(bug, admin_user),
                storage_key="attachments/a/b/c.txt",
                status=AttachmentStatus.PENDING,
                removed_at=timezone.now(),
            )

    def test_uploaded_without_uploaded_at_rejected(self, bug, admin_user):
        with pytest.raises(IntegrityError), transaction.atomic():
            Attachment.objects.create(
                **_base_kwargs(bug, admin_user),
                storage_key="attachments/a/b/c.txt",
                status=AttachmentStatus.UPLOADED,
            )

    def test_uploaded_with_failed_at_rejected(self, bug, admin_user):
        now = timezone.now()
        with pytest.raises(IntegrityError), transaction.atomic():
            Attachment.objects.create(
                **_base_kwargs(bug, admin_user),
                storage_key="attachments/a/b/c.txt",
                status=AttachmentStatus.UPLOADED,
                uploaded_at=now,
                failed_at=now,
            )

    def test_failed_without_failed_at_rejected(self, bug, admin_user):
        with pytest.raises(IntegrityError), transaction.atomic():
            Attachment.objects.create(
                **_base_kwargs(bug, admin_user),
                storage_key="attachments/a/b/c.txt",
                status=AttachmentStatus.FAILED,
            )

    def test_failed_with_removed_at_rejected(self, bug, admin_user):
        now = timezone.now()
        with pytest.raises(IntegrityError), transaction.atomic():
            Attachment.objects.create(
                **_base_kwargs(bug, admin_user),
                storage_key="attachments/a/b/c.txt",
                status=AttachmentStatus.FAILED,
                failed_at=now,
                removed_at=now,
            )


@pytest.mark.django_db
class TestSizeConstraint:
    def test_zero_size_rejected(self, bug, admin_user):
        with pytest.raises(IntegrityError), transaction.atomic():
            Attachment.objects.create(
                **{**_base_kwargs(bug, admin_user), "size_bytes": 0},
                storage_key="attachments/a/b/c.txt",
            )

    def test_negative_size_rejected(self, bug, admin_user):
        with pytest.raises(IntegrityError), transaction.atomic():
            Attachment.objects.create(
                **{**_base_kwargs(bug, admin_user), "size_bytes": -1},
                storage_key="attachments/a/b/c.txt",
            )


@pytest.mark.django_db
class TestStorageKeyUniqueness:
    def test_duplicate_storage_key_rejected(self, bug, admin_user):
        Attachment.objects.create(
            **_base_kwargs(bug, admin_user), storage_key="attachments/dup.txt"
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            Attachment.objects.create(
                **_base_kwargs(bug, admin_user), storage_key="attachments/dup.txt"
            )
