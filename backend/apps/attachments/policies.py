"""Domain-level authorization for the attachments app.

Mirrors apps.comments.policies exactly: independently declared role sets
(not imported from comments/bugs), used from both apps.attachments.services
(fine-grained checks) and apps.attachments.serializers (the can_remove UI
hint).
"""

from apps.organizations.models import CommunityRole

# Same roles that may comment (apps.comments.policies.CAN_COMMENT_ROLES) —
# kept as its own set rather than imported, so a future change to comment
# eligibility doesn't silently change who may upload. Viewer is deliberately
# excluded: it is the read-only role.
CAN_UPLOAD_ROLES = frozenset(
    {
        CommunityRole.ADMINISTRATOR,
        CommunityRole.DEVELOPER,
        CommunityRole.QA,
        CommunityRole.REPORTER,
    }
)

# Moderation (remove anyone's attachment, including after archive) is
# administrator-only — mirrors apps.comments.policies.MODERATOR_ROLES.
MODERATOR_ROLES = frozenset({CommunityRole.ADMINISTRATOR})


class AttachmentPermissionDenied(Exception):
    pass


def can_upload(membership) -> bool:
    return membership is not None and membership.role in CAN_UPLOAD_ROLES


def is_uploader(attachment, user) -> bool:
    return user is not None and attachment.uploaded_by_id == user.pk


def is_moderator(membership) -> bool:
    return membership is not None and membership.role in MODERATOR_ROLES
