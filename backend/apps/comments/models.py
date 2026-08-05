from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import OrganizationScopedModel

MAX_COMMENT_BODY_LENGTH = 10_000


class CommentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    DELETED = "deleted", "Deleted"
    REDACTED = "redacted", "Redacted"


class Comment(OrganizationScopedModel):
    """A discussion entry on a bug.

    `body` is cleared — not just hidden — the moment `status` leaves ACTIVE; delete
    and redact (apps.comments.services) are both irreversible, with no recovery
    path. `edited_at` reflects only a genuine content change (see
    services.edit_comment's no-op short-circuit) and is left untouched by
    delete/redact, which use their own `deleted_at`/`redacted_at` instead — the
    three timestamps are mutually exclusive by construction, enforced below.
    """

    bug = models.ForeignKey("bugs.Bug", on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="authored_comments"
    )
    body = models.TextField(max_length=MAX_COMMENT_BODY_LENGTH, blank=True)
    status = models.CharField(
        max_length=10, choices=CommentStatus.choices, default=CommentStatus.ACTIVE
    )
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    redacted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # Ties status to exactly the timestamp(s) that status implies — not just
            # "not both set", but the full valid state space: active comments carry
            # neither, deleted comments carry exactly deleted_at, redacted comments
            # carry exactly redacted_at.
            models.CheckConstraint(
                condition=(
                    Q(
                        status=CommentStatus.ACTIVE,
                        deleted_at__isnull=True,
                        redacted_at__isnull=True,
                    )
                    | Q(
                        status=CommentStatus.DELETED,
                        deleted_at__isnull=False,
                        redacted_at__isnull=True,
                    )
                    | Q(
                        status=CommentStatus.REDACTED,
                        redacted_at__isnull=False,
                        deleted_at__isnull=True,
                    )
                ),
                name="comment_status_timestamp_consistency",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "bug", "created_at"]),
        ]
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"Comment {self.id} on bug {self.bug_id}"


class Mention(OrganizationScopedModel):
    """A structured record that `comment` names `mentioned_user`.

    Parsed from the comment's raw markdown source (never rendered HTML) and
    revalidated against OrganizationMembership at creation time — see
    apps.comments.mentions. The unique constraint below is what makes repeated
    @mentions of the same person within one comment collapse to a single row
    (and, later, a single notification) rather than needing de-duplication at
    every read site.
    """

    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="mentions")
    mentioned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comment_mentions"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["comment", "mentioned_user"], name="unique_mention_per_comment_user"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "mentioned_user"]),
        ]

    def __str__(self) -> str:
        return f"Mention of {self.mentioned_user_id} in comment {self.comment_id}"
