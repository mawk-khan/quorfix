from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.comments import policies
from apps.comments.models import MAX_COMMENT_BODY_LENGTH, Comment, CommentStatus, Mention


class MentionRefSerializer(serializers.ModelSerializer):
    mentioned_user = UserSerializer(read_only=True)

    class Meta:
        model = Mention
        fields = ["id", "mentioned_user"]
        read_only_fields = fields


class CommentSerializer(serializers.ModelSerializer):
    """`can_edit`/`can_delete`/`can_redact` are the same policy functions
    apps.comments.services enforces server-side — the frontend must treat them
    as UI hints only, never as its own authorization decision, but they save it
    from re-deriving the edit-window/role matrix client-side."""

    author = UserSerializer(read_only=True)
    mentions = MentionRefSerializer(many=True, read_only=True)
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    can_redact = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "author",
            "body",
            "status",
            "mentions",
            "edited_at",
            "deleted_at",
            "redacted_at",
            "can_edit",
            "can_delete",
            "can_redact",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _viewer(self):
        request = self.context.get("request")
        if request is None or not getattr(request.user, "is_authenticated", False):
            return None
        return request.user

    def _membership(self):
        return self.context.get("membership")

    def get_can_edit(self, obj) -> bool:
        viewer = self._viewer()
        return (
            obj.status == CommentStatus.ACTIVE
            and policies.is_comment_author(obj, viewer)
            and policies.is_within_edit_window(obj)
        )

    def get_can_delete(self, obj) -> bool:
        if obj.status != CommentStatus.ACTIVE:
            return False
        viewer = self._viewer()
        membership = self._membership()
        if policies.is_moderator(membership):
            return True
        return policies.is_comment_author(obj, viewer) and policies.is_within_edit_window(obj)

    def get_can_redact(self, obj) -> bool:
        return obj.status == CommentStatus.ACTIVE and policies.is_moderator(self._membership())


class CommentCreateSerializer(serializers.Serializer):
    # Blank/whitespace-only and max-length are enforced authoritatively in
    # apps.comments.services._normalize_body (the single source of truth,
    # shared with CommentUpdateSerializer below) — this field only bounds the
    # raw payload shape.
    body = serializers.CharField(max_length=MAX_COMMENT_BODY_LENGTH)


class CommentUpdateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=MAX_COMMENT_BODY_LENGTH)
