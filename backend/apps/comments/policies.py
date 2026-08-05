"""Domain-level authorization for the comments app.

Mirrors apps.bugs.policies: these functions are the single source of truth for
"who can do what", called from apps.comments.services for the fine-grained,
object-level checks and reflected back out through
apps.comments.serializers' can_edit/can_delete/can_redact fields so the API
response tells the client what it may currently do without duplicating this
logic client-side.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.organizations.models import CommunityRole

# Same roles that may create a bug (apps.bugs.policies.CREATE_ROLES) — kept as
# its own set rather than imported, so a future change to bug-creation
# eligibility doesn't silently change who may comment. Viewer is deliberately
# excluded: it is the read-only role.
CAN_COMMENT_ROLES = frozenset(
    {
        CommunityRole.ADMINISTRATOR,
        CommunityRole.DEVELOPER,
        CommunityRole.QA,
        CommunityRole.REPORTER,
    }
)

# Moderation (redact, or delete someone else's comment) is administrator-only.
# Nobody — including administrators — may silently rewrite another user's
# comment body; the only cross-user powers are redact and delete.
MODERATOR_ROLES = frozenset({CommunityRole.ADMINISTRATOR})


class CommentPermissionDenied(Exception):
    pass


def can_comment(membership) -> bool:
    return membership is not None and membership.role in CAN_COMMENT_ROLES


def is_comment_author(comment, user) -> bool:
    return user is not None and comment.author_id == user.pk


def is_moderator(membership) -> bool:
    return membership is not None and membership.role in MODERATOR_ROLES


def is_within_edit_window(comment, now=None) -> bool:
    """Inclusive of the exact boundary instant: an edit/delete submitted at
    precisely created_at + COMMENT_EDIT_WINDOW_MINUTES still succeeds; anything
    strictly after does not."""
    now = now or timezone.now()
    window = timedelta(minutes=settings.COMMENT_EDIT_WINDOW_MINUTES)
    return now <= comment.created_at + window
