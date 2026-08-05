from django.db.models import QuerySet

from apps.attachments.models import Attachment, AttachmentStatus


def get_attachments_for_bug(bug) -> QuerySet[Attachment]:
    """Bare organization+bug-scoped queryset for get_object_or_404 lookups —
    mirrors apps.comments.selectors.get_comments_for_bug."""
    return Attachment.objects.filter(organization=bug.organization, bug=bug)


def get_attachment_for_bug(bug) -> QuerySet[Attachment]:
    """select_related version for single-object and list lookups."""
    return get_attachments_for_bug(bug).select_related("uploaded_by", "bug__project")


def list_attachments_for_bug(bug) -> QuerySet[Attachment]:
    """Oldest-first with a stable id tie-breaker — matches comments'
    convention for user-added content on a bug (unlike the newest-first
    activity feed, which is a system log). Only ever surfaces attachments
    that are actually visible: pending/failed/removed attachments must never
    look like normal downloadable attachments."""
    return (
        get_attachment_for_bug(bug)
        .filter(status=AttachmentStatus.UPLOADED, removed_at__isnull=True)
        .order_by("created_at", "id")
    )


def get_attachment_for_organization(organization) -> QuerySet[Attachment]:
    """Bare organization-scoped queryset for the un-nested upload-bytes
    endpoint, which has no bug_id in its URL at all — the Attachment's own
    `organization` FK is what tenant-scopes it. select_related so
    _check_bug_attachable never costs an extra query."""
    return Attachment.objects.filter(organization=organization).select_related(
        "bug__project", "uploaded_by"
    )
