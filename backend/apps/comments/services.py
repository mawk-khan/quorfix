from django.db import transaction
from django.utils import timezone

from apps.comments import mentions, policies
from apps.comments.models import MAX_COMMENT_BODY_LENGTH, Comment, CommentStatus, Mention
from apps.comments.policies import CommentPermissionDenied


class CommentServiceError(Exception):
    """Common base for every domain exception this module raises, so the view
    layer can dispatch on one type instead of an ever-growing except tuple. Not
    raised directly."""


class BugArchived(CommentServiceError):
    pass


class ProjectArchived(CommentServiceError):
    pass


class InvalidCommentBody(CommentServiceError):
    pass


class CommentNotActive(CommentServiceError):
    pass


class EditWindowExpired(CommentServiceError):
    pass


def _check_bug_commentable(bug) -> None:
    """Holds the same invariant apps.bugs.services._check_mutable holds for the
    bug's own fields: neither the bug nor its project may be archived. Applies
    to comment creation, editing, and author-initiated deletion — deliberately
    NOT to administrator moderation (delete-any/redact), which must keep
    working on an archived bug/project; see delete_comment and redact_comment.
    Requires `bug.project` to already be select_related — see
    apps.bugs.selectors.get_bug_for_organization, which every view in this
    app uses to fetch it."""
    if bug.archived_at is not None:
        raise BugArchived()
    if bug.project.archived_at is not None:
        raise ProjectArchived()


def _normalize_body(body: str) -> str:
    normalized = body.strip()
    if not normalized or len(normalized) > MAX_COMMENT_BODY_LENGTH:
        raise InvalidCommentBody()
    return normalized


def _record(bug, actor, verb, **kwargs):
    from apps.activities.services import record_bug_activity

    return record_bug_activity(bug=bug, actor=actor, verb=verb, **kwargs)


def _create_mentions(bug, comment, actor) -> list[Mention]:
    from apps.activities.models import ActivityVerb

    candidate_ids = mentions.extract_mention_user_ids(comment.body)
    valid_ids = mentions.resolve_mentions(bug.organization, candidate_ids)
    if not valid_ids:
        return []

    created = Mention.objects.bulk_create(
        [
            Mention(organization=bug.organization, comment=comment, mentioned_user_id=uid)
            for uid in valid_ids
        ]
    )
    for mention in created:
        _record(
            bug,
            actor,
            ActivityVerb.MENTION_CREATED,
            metadata={
                "comment_id": str(comment.id),
                "mentioned_user_id": str(mention.mentioned_user_id),
            },
        )
    return created


# -- create ------------------------------------------------------------


@transaction.atomic
def create_comment(*, bug, author, membership, body: str) -> Comment:
    from apps.activities.models import ActivityVerb

    if not policies.can_comment(membership):
        raise CommentPermissionDenied()
    _check_bug_commentable(bug)
    normalized_body = _normalize_body(body)

    comment = Comment.objects.create(
        organization=bug.organization, bug=bug, author=author, body=normalized_body
    )
    _record(bug, author, ActivityVerb.COMMENT_ADDED, metadata={"comment_id": str(comment.id)})
    _create_mentions(bug, comment, author)
    return comment


# -- edit ----------------------------------------------------------------


@transaction.atomic
def edit_comment(*, bug, comment, actor, membership, body: str) -> Comment:
    from apps.activities.models import ActivityVerb

    locked = Comment.objects.select_for_update().select_related("author").get(pk=comment.pk)

    if not policies.is_comment_author(locked, actor):
        raise CommentPermissionDenied()
    _check_bug_commentable(bug)
    if locked.status != CommentStatus.ACTIVE:
        raise CommentNotActive()
    if not policies.is_within_edit_window(locked):
        raise EditWindowExpired()

    normalized_body = _normalize_body(body)
    if normalized_body == locked.body:
        return locked  # no-op edit — no activity, no edited_at bump

    locked.body = normalized_body
    locked.edited_at = timezone.now()
    locked.save(update_fields=["body", "edited_at"])
    _record(bug, actor, ActivityVerb.COMMENT_EDITED, metadata={"comment_id": str(locked.id)})
    return locked


# -- delete / redact -------------------------------------------------------


@transaction.atomic
def delete_comment(*, bug, comment, actor, membership) -> Comment:
    from apps.activities.models import ActivityVerb

    locked = Comment.objects.select_for_update().select_related("author").get(pk=comment.pk)

    is_author = policies.is_comment_author(locked, actor)
    is_moderator = policies.is_moderator(membership)
    if not (is_author or is_moderator):
        raise CommentPermissionDenied()
    if locked.status != CommentStatus.ACTIVE:
        raise CommentNotActive()
    if not is_moderator:
        # Author-initiated deletion is still bound by the same mutability
        # invariant as every other author-side comment mutation (creation,
        # editing). Administrator moderation is deliberately exempt from both
        # this check and the edit window — moderation must keep working on an
        # archived bug/project, and at any time, not just within the window.
        _check_bug_commentable(bug)
        if not policies.is_within_edit_window(locked):
            raise EditWindowExpired()

    locked.body = ""
    locked.status = CommentStatus.DELETED
    locked.deleted_at = timezone.now()
    locked.save(update_fields=["body", "status", "deleted_at"])
    _record(bug, actor, ActivityVerb.COMMENT_DELETED, metadata={"comment_id": str(locked.id)})
    return locked


@transaction.atomic
def redact_comment(*, bug, comment, actor, membership) -> Comment:
    from apps.activities.models import ActivityVerb

    locked = Comment.objects.select_for_update().select_related("author").get(pk=comment.pk)

    if not policies.is_moderator(membership):
        raise CommentPermissionDenied()
    if locked.status != CommentStatus.ACTIVE:
        raise CommentNotActive()
    # No bug/project mutability check here, unlike create/edit/author-delete:
    # redaction is a moderation action and must remain possible regardless of
    # archive state — see delete_comment's identical administrator exemption.

    locked.body = ""
    locked.status = CommentStatus.REDACTED
    locked.redacted_at = timezone.now()
    locked.save(update_fields=["body", "status", "redacted_at"])
    _record(bug, actor, ActivityVerb.COMMENT_REDACTED, metadata={"comment_id": str(locked.id)})
    return locked
