from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from apps.attachments import selectors, services
from apps.attachments.policies import AttachmentPermissionDenied
from apps.attachments.serializers import (
    AttachmentInitiateResponseSerializer,
    AttachmentInitiateSerializer,
    AttachmentSerializer,
)
from apps.bugs.selectors import get_bug_for_organization
from apps.core.pagination import BoundedPageNumberPagination
from apps.organizations.permissions import IsOrganizationMember

# AttachmentPermissionDenied lives in apps.attachments.policies (imported by
# services.py, not defined there) — mirrors apps.comments.views' identical
# split, for the identical reason. UnsupportedContentType/AttachmentTooLarge
# are raised by apps.attachments.validators and merely re-exported through
# services — they are not AttachmentServiceError subclasses, so they're
# listed here explicitly too, or a validation failure would surface as an
# uncaught 500 instead of a structured 400.
_HANDLED_ATTACHMENT_ERRORS = (
    services.AttachmentServiceError,
    AttachmentPermissionDenied,
    services.UnsupportedContentType,
    services.AttachmentTooLarge,
)


def _detail_response(description: str) -> OpenApiResponse:
    return OpenApiResponse(
        response={"type": "object", "properties": {"detail": {"type": "string"}}},
        description=description,
    )


_FORBIDDEN_RESPONSE = _detail_response("The caller is authenticated but not permitted to do this.")
_NOT_FOUND_RESPONSE = _detail_response(
    "No bug or attachment with this id exists in the caller's active organization."
)
_VALIDATION_ERROR_RESPONSE = OpenApiResponse(
    response={
        "type": "object",
        "additionalProperties": {"type": "array", "items": {"type": "string"}},
    },
    description="Structured per-field validation errors.",
)
_CONFLICT_RESPONSE = _detail_response(
    "The attachment is not in a state that allows this action, or the bug/project is archived."
)

_ERROR_RESPONSES: dict[type[Exception], tuple[int, dict]] = {
    services.BugArchived: (
        status.HTTP_409_CONFLICT,
        {"detail": "This bug is archived. Attachments cannot be added or changed."},
    ),
    services.ProjectArchived: (
        status.HTTP_409_CONFLICT,
        {"detail": "This bug's project is archived. Attachments cannot be added or changed."},
    ),
    services.UnsupportedContentType: (
        status.HTTP_400_BAD_REQUEST,
        {"content_type": ["This file type is not supported."]},
    ),
    services.AttachmentTooLarge: (
        status.HTTP_400_BAD_REQUEST,
        {"size_bytes": ["File exceeds the maximum allowed size."]},
    ),
    services.AttachmentNotPending: (
        status.HTTP_409_CONFLICT,
        {"detail": "This upload has already been completed or failed."},
    ),
    services.UploadVerificationFailed: (
        status.HTTP_409_CONFLICT,
        {"detail": "The uploaded file did not match the declared size."},
    ),
    services.SignatureMismatch: (
        status.HTTP_409_CONFLICT,
        {"detail": "The uploaded file's content does not match the declared type."},
    ),
    services.AttachmentNotAvailable: (
        status.HTTP_409_CONFLICT,
        {"detail": "This attachment has already been removed."},
    ),
    AttachmentPermissionDenied: (
        status.HTTP_403_FORBIDDEN,
        {"detail": "You do not have permission to perform this action."},
    ),
}


class AttachmentErrorHandlingMixin:
    def _attachment_context(self, request) -> dict:
        return {"request": request, "membership": getattr(request, "membership", None)}

    def handle_attachment_service_error(self, exc: Exception) -> Response:
        for exc_type, (code, body) in _ERROR_RESPONSES.items():
            if isinstance(exc, exc_type):
                return Response(body, status=code)
        raise exc

    def _get_bug(self, request, bug_id):
        return get_object_or_404(get_bug_for_organization(request.organization), pk=bug_id)

    def _get_attachment(self, bug, attachment_id):
        return get_object_or_404(selectors.get_attachment_for_bug(bug), pk=attachment_id)

    def _serialize(self, attachment, request) -> dict:
        return AttachmentSerializer(attachment, context=self._attachment_context(request)).data


class AttachmentListCreateView(AttachmentErrorHandlingMixin, APIView):
    """List/initiate attachments on a bug. GET is open to any org member
    (matching comments/bugs); POST is fine-grained-gated inside
    apps.attachments.services.initiate_upload (policies.can_upload)."""

    permission_classes = [IsOrganizationMember]

    @extend_schema(
        responses={
            200: AttachmentSerializer(many=True),
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
        }
    )
    def get(self, request, bug_id=None):
        bug = self._get_bug(request, bug_id)
        queryset = selectors.list_attachments_for_bug(bug)

        paginator = BoundedPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        context = self._attachment_context(request)
        serializer = AttachmentSerializer(page, many=True, context=context)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=AttachmentInitiateSerializer,
        responses={
            201: AttachmentInitiateResponseSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    def post(self, request, bug_id=None):
        bug = self._get_bug(request, bug_id)
        serializer = AttachmentInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            attachment = services.initiate_upload(
                bug=bug,
                uploader=request.user,
                membership=request.membership,
                original_filename=data["original_filename"],
                content_type=data["content_type"],
                size_bytes=data["size_bytes"],
            )
        except _HANDLED_ATTACHMENT_ERRORS as exc:
            return self.handle_attachment_service_error(exc)

        upload_url = reverse(
            "attachment-upload-bytes", kwargs={"attachment_id": attachment.id}, request=request
        )
        return Response(
            {
                "attachment": self._serialize(attachment, request),
                "upload": {"method": "PUT", "url": upload_url},
            },
            status=status.HTTP_201_CREATED,
        )


class AttachmentDetailView(AttachmentErrorHandlingMixin, APIView):
    """Soft-removes a single attachment. Returns 200 with the updated
    representation, not 204 — matches apps.comments.views' DELETE style."""

    permission_classes = [IsOrganizationMember]

    @extend_schema(
        request=None,
        responses={
            200: AttachmentSerializer,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    def delete(self, request, bug_id=None, attachment_id=None):
        bug = self._get_bug(request, bug_id)
        attachment = self._get_attachment(bug, attachment_id)

        try:
            attachment = services.remove_attachment(
                bug=bug, attachment=attachment, actor=request.user, membership=request.membership
            )
        except _HANDLED_ATTACHMENT_ERRORS as exc:
            return self.handle_attachment_service_error(exc)
        return Response(self._serialize(attachment, request))


class AttachmentDownloadView(AttachmentErrorHandlingMixin, APIView):
    """Streams the file directly — the only download path that exists for the
    local backend; there is no separate signed-URL indirection (see Chunk 2
    plan)."""

    permission_classes = [IsOrganizationMember]

    @extend_schema(
        responses={
            200: OpenApiResponse(description="The file, streamed as an attachment."),
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
        }
    )
    def get(self, request, bug_id=None, attachment_id=None):
        from django.http import FileResponse

        bug = self._get_bug(request, bug_id)
        attachment = self._get_attachment(bug, attachment_id)
        file_path = services.get_download_path(attachment=attachment)  # raises Http404 itself

        response = FileResponse(
            open(file_path, "rb"),
            as_attachment=True,
            filename=attachment.original_filename,
            content_type=attachment.content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


class AttachmentUploadBytesView(AttachmentErrorHandlingMixin, APIView):
    """Local-only, un-nested (attachment id alone resolves organization/bug —
    there is no bug_id in this URL). Tenant scoping happens via the
    Attachment's own organization FK, exactly like every other lookup in this
    app, so a cross-org attachment id 404s the same as everywhere else."""

    permission_classes = [IsOrganizationMember]
    parser_classes = [MultiPartParser]

    _UPLOAD_REQUEST_SCHEMA = {
        "multipart/form-data": {
            "type": "object",
            "properties": {"file": {"type": "string", "format": "binary"}},
        }
    }

    @extend_schema(
        request=_UPLOAD_REQUEST_SCHEMA,
        responses={
            200: AttachmentSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    def put(self, request, attachment_id=None):
        attachment = get_object_or_404(
            selectors.get_attachment_for_organization(request.organization), pk=attachment_id
        )
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response(
                {"file": ["No file was submitted."]}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            attachment = services.receive_local_upload(
                attachment=attachment, actor=request.user, uploaded_file=uploaded_file
            )
        except _HANDLED_ATTACHMENT_ERRORS as exc:
            return self.handle_attachment_service_error(exc)
        return Response(self._serialize(attachment, request))
