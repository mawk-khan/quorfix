from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.attachments import policies
from apps.attachments.models import Attachment, AttachmentStatus
from apps.attachments.validators import ALLOWED_CONTENT_TYPES


class AttachmentSerializer(serializers.ModelSerializer):
    """`can_remove` is the same policy functions apps.attachments.services
    enforces server-side — a UI hint only, doesn't factor in archive state
    (matching the same documented limitation as apps.comments.serializers'
    can_edit/can_delete/can_redact)."""

    uploaded_by = UserSerializer(read_only=True)
    can_remove = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = [
            "id",
            "uploaded_by",
            "original_filename",
            "content_type",
            "size_bytes",
            "status",
            "scan_status",
            "uploaded_at",
            "removed_at",
            "can_remove",
            "created_at",
        ]
        read_only_fields = fields

    def _viewer(self):
        request = self.context.get("request")
        if request is None or not getattr(request.user, "is_authenticated", False):
            return None
        return request.user

    def get_can_remove(self, obj) -> bool:
        if obj.status != AttachmentStatus.UPLOADED or obj.removed_at is not None:
            return False
        membership = self.context.get("membership")
        if policies.is_moderator(membership):
            return True
        return policies.is_uploader(obj, self._viewer())


class AttachmentInitiateSerializer(serializers.Serializer):
    original_filename = serializers.CharField(max_length=255)
    content_type = serializers.ChoiceField(choices=sorted(ALLOWED_CONTENT_TYPES))
    size_bytes = serializers.IntegerField(min_value=1)


class UploadInstructionsSerializer(serializers.Serializer):
    method = serializers.CharField()
    url = serializers.CharField()


class AttachmentInitiateResponseSerializer(serializers.Serializer):
    """Response shape for POST .../attachments/ — a real (if never
    model-backed) serializer, not a hand-built OpenAPI dict, so
    drf-spectacular can actually introspect it: a raw serializer *class*
    embedded inside a manually written schema dict isn't something
    spectacular resolves, it just gets passed through literally and breaks
    schema generation."""

    attachment = AttachmentSerializer()
    upload = UploadInstructionsSerializer()
