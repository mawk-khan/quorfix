import logging
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.attachments import policies, validators
from apps.attachments.models import Attachment, AttachmentStatus
from apps.attachments.policies import AttachmentPermissionDenied
from apps.attachments.providers import get_storage_provider, hash_storage_key

# Re-exported, not re-defined: validators.validate_content_type/validate_size
# raise these directly, so services.py (and, through it, views.py's
# exception-mapping table) must reference the exact same classes rather than
# a same-named lookalike that would never actually be raised.
from apps.attachments.validators import (  # noqa: F401 — re-exported for apps.attachments.views
    AttachmentTooLarge,
    UnsupportedContentType,
)
from apps.core.task_correlation import correlation_headers

logger = logging.getLogger(__name__)


class AttachmentServiceError(Exception):
    """Common base for every domain exception this module raises, so the view
    layer can dispatch on one type instead of an ever-growing except tuple. Not
    raised directly. NOTE: AttachmentTooLarge/UnsupportedContentType (imported
    above from validators) are NOT subclasses of this — see
    apps.attachments.views._HANDLED_ATTACHMENT_ERRORS, which lists them
    alongside this base explicitly."""


class BugArchived(AttachmentServiceError):
    pass


class ProjectArchived(AttachmentServiceError):
    pass


class AttachmentNotPending(AttachmentServiceError):
    pass


class UploadVerificationFailed(AttachmentServiceError):
    pass


class SignatureMismatch(AttachmentServiceError):
    pass


class AttachmentNotAvailable(AttachmentServiceError):
    pass


def _check_bug_attachable(bug) -> None:
    """Holds the same invariant apps.comments.services._check_bug_commentable
    holds: neither the bug nor its project may be archived. Applies to
    initiation and uploader-initiated removal — deliberately NOT to
    administrator moderation (remove-any), which must keep working on an
    archived bug/project. Requires `bug.project` to already be
    select_related."""
    if bug.archived_at is not None:
        raise BugArchived()
    if bug.project.archived_at is not None:
        raise ProjectArchived()


def _record(bug, actor, verb, **kwargs):
    from apps.activities.services import record_bug_activity

    return record_bug_activity(bug=bug, actor=actor, verb=verb, **kwargs)


def _build_storage_key(*, organization_id, bug_id, attachment_id, content_type) -> str:
    extension = validators.extension_for_content_type(content_type)
    return f"attachments/{organization_id}/{bug_id}/{attachment_id}{extension}"


def _mark_failed(attachment: Attachment) -> None:
    with transaction.atomic():
        locked = Attachment.objects.select_for_update().get(pk=attachment.pk)
        if locked.status != AttachmentStatus.PENDING:
            return  # already resolved by a concurrent request — nothing to do
        locked.status = AttachmentStatus.FAILED
        locked.failed_at = timezone.now()
        locked.save(update_fields=["status", "failed_at"])


def _maybe_scan(attachment: Attachment) -> None:
    """Checks the malware-scanning extension point. Community never registers
    a scanner here (see apps.attachments.scanning), so this is a no-op today
    — the hook is real, but there is nothing yet to drive scan_status past
    not_scanned."""
    from apps.core.registries import capability_registry

    scanner = capability_registry.get("malware_scanning")
    if scanner is None:
        return


# -- initiate --------------------------------------------------------------


@transaction.atomic
def initiate_upload(
    *, bug, uploader, membership, original_filename: str, content_type: str, size_bytes: int
) -> Attachment:
    if not policies.can_upload(membership):
        raise AttachmentPermissionDenied()
    _check_bug_attachable(bug)
    validators.validate_content_type(content_type)
    validators.validate_size(size_bytes, max_size_bytes=settings.MAX_ATTACHMENT_SIZE_BYTES)
    safe_filename = validators.sanitize_filename(original_filename)

    attachment_id = uuid.uuid4()
    storage_key = _build_storage_key(
        organization_id=bug.organization_id,
        bug_id=bug.id,
        attachment_id=attachment_id,
        content_type=content_type,
    )
    return Attachment.objects.create(
        id=attachment_id,
        organization=bug.organization,
        bug=bug,
        uploaded_by=uploader,
        original_filename=safe_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_key=storage_key,
    )


# -- local upload ------------------------------------------------------------


def receive_local_upload(*, attachment: Attachment, actor, uploaded_file) -> Attachment:
    """Validates, streams, and finalizes a local upload in one flow — there is
    no separate /complete/ step for the local backend (see Chunk 2 plan).

    The slow part (streaming bytes to disk) deliberately happens outside any
    DB transaction, so a multi-second write never holds a row lock. Only the
    final status flip is wrapped in a short, locked transaction, which is
    what actually closes the race against a genuine concurrent double-submit.
    """
    from apps.activities.models import ActivityVerb

    if not policies.is_uploader(attachment, actor):
        raise AttachmentPermissionDenied()
    if attachment.status != AttachmentStatus.PENDING:
        raise AttachmentNotPending()

    bug = attachment.bug  # select_related by the caller (get_attachment_for_organization)
    _check_bug_attachable(bug)

    if uploaded_file.size != attachment.size_bytes:
        _mark_failed(attachment)
        raise UploadVerificationFailed()

    if not validators.verify_uploaded_content(attachment.content_type, uploaded_file):
        _mark_failed(attachment)
        raise SignatureMismatch()

    provider = get_storage_provider()
    provider.save_stream(attachment.storage_key, uploaded_file.chunks())

    actual_size = provider.head(attachment.storage_key)
    if actual_size != attachment.size_bytes:
        _mark_failed(attachment)
        raise UploadVerificationFailed()

    with transaction.atomic():
        locked = Attachment.objects.select_for_update().get(pk=attachment.pk)
        if locked.status != AttachmentStatus.PENDING:
            raise AttachmentNotPending()
        locked.status = AttachmentStatus.UPLOADED
        locked.uploaded_at = timezone.now()
        locked.save(update_fields=["status", "uploaded_at"])
        _record(
            bug,
            actor,
            ActivityVerb.ATTACHMENT_ADDED,
            metadata={
                "attachment_id": str(locked.id),
                "original_filename": locked.original_filename,
                "content_type": locked.content_type,
                "size_bytes": locked.size_bytes,
            },
        )
    _maybe_scan(locked)
    return locked


# -- download ----------------------------------------------------------------


def get_download_path(*, attachment: Attachment):
    """Not a mutation. Raises Http404 directly (not a service exception) when
    the attachment isn't currently visible — a pending/failed/removed
    attachment behaves exactly as "doesn't exist" for read purposes."""
    from django.http import Http404

    if attachment.status != AttachmentStatus.UPLOADED or attachment.removed_at is not None:
        raise Http404()

    provider = get_storage_provider()
    path = provider.resolve_download(attachment.storage_key)
    if path is None:
        logger.error(
            "Attachment %s is marked uploaded but its storage object (%s) is missing",
            attachment.id,
            hash_storage_key(attachment.storage_key),
        )
        raise Http404()
    return path


# -- removal -------------------------------------------------------------


@transaction.atomic
def remove_attachment(*, bug, attachment: Attachment, actor, membership) -> Attachment:
    from apps.activities.models import ActivityVerb

    locked = Attachment.objects.select_for_update().get(pk=attachment.pk)

    is_uploader_ = policies.is_uploader(locked, actor)
    is_moderator_ = policies.is_moderator(membership)
    if not (is_uploader_ or is_moderator_):
        raise AttachmentPermissionDenied()
    if locked.status != AttachmentStatus.UPLOADED or locked.removed_at is not None:
        raise AttachmentNotAvailable()
    if not is_moderator_:
        _check_bug_attachable(bug)

    locked.removed_at = timezone.now()
    locked.save(update_fields=["removed_at"])
    _record(
        bug,
        actor,
        ActivityVerb.ATTACHMENT_REMOVED,
        metadata={
            "attachment_id": str(locked.id),
            "original_filename": locked.original_filename,
            "content_type": locked.content_type,
            "size_bytes": locked.size_bytes,
        },
    )

    storage_key = locked.storage_key

    def _dispatch_cleanup():
        from apps.attachments.tasks import delete_attachment_object

        try:
            delete_attachment_object.apply_async(args=[storage_key], headers=correlation_headers())
        except Exception:
            # A broker outage must never surface as a failure of the removal
            # itself — the DB state (removed_at) already committed by the
            # time this callback runs.
            logger.exception(
                "Failed to dispatch attachment cleanup task for %s", hash_storage_key(storage_key)
            )

    transaction.on_commit(_dispatch_cleanup)
    return locked
