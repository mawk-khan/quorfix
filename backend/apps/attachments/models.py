from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import OrganizationScopedModel


class AttachmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    UPLOADED = "uploaded", "Uploaded"
    FAILED = "failed", "Failed"


class ScanStatus(models.TextChoices):
    NOT_SCANNED = "not_scanned", "Not scanned"
    PENDING = "pending", "Pending"
    CLEAN = "clean", "Clean"
    INFECTED = "infected", "Infected"


class Attachment(OrganizationScopedModel):
    """A file attached to a bug.

    `status` is a one-way upload lifecycle: pending -> uploaded, or
    pending -> failed. There is no retry-on-the-same-row and no path back to
    pending — a failed or abandoned upload is never resurrected; the client
    calls initiate_upload again for a fresh attempt (fresh id, fresh storage
    key). Removal (`removed_at`) is a separate, orthogonal soft-delete axis
    layered only on top of `uploaded` — not a fourth status value — enforced
    by the constraint below rather than a status="removed" choice.

    `storage_key` is entirely server-generated (organization id + bug id +
    attachment id + an extension looked up from the validated content_type —
    see apps.attachments.services._build_storage_key); `original_filename` is
    display metadata only and never participates in it.
    """

    bug = models.ForeignKey("bugs.Bug", on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_attachments"
    )
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField()
    storage_key = models.CharField(max_length=500, editable=False, unique=True)
    status = models.CharField(
        max_length=10, choices=AttachmentStatus.choices, default=AttachmentStatus.PENDING
    )
    scan_status = models.CharField(
        max_length=12, choices=ScanStatus.choices, default=ScanStatus.NOT_SCANNED
    )
    uploaded_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # removed_at is deliberately unconstrained (nullable either way)
            # only in the "uploaded" branch — that's what makes removal valid
            # only from the uploaded state.
            models.CheckConstraint(
                condition=(
                    Q(
                        status=AttachmentStatus.PENDING,
                        uploaded_at__isnull=True,
                        failed_at__isnull=True,
                        removed_at__isnull=True,
                    )
                    | Q(
                        status=AttachmentStatus.UPLOADED,
                        uploaded_at__isnull=False,
                        failed_at__isnull=True,
                    )
                    | Q(
                        status=AttachmentStatus.FAILED,
                        uploaded_at__isnull=True,
                        failed_at__isnull=False,
                        removed_at__isnull=True,
                    )
                ),
                name="attachment_status_timestamp_consistency",
            ),
            models.CheckConstraint(condition=Q(size_bytes__gt=0), name="attachment_size_positive"),
        ]
        indexes = [
            models.Index(fields=["organization", "bug", "status", "removed_at"]),
            models.Index(fields=["organization", "status"]),
        ]
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.original_filename} on bug {self.bug_id}"
