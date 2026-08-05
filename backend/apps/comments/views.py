from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bugs.selectors import get_bug_for_organization
from apps.comments import selectors, services
from apps.comments.policies import CommentPermissionDenied
from apps.comments.serializers import (
    CommentCreateSerializer,
    CommentSerializer,
    CommentUpdateSerializer,
)
from apps.core.pagination import BoundedPageNumberPagination
from apps.organizations.permissions import IsOrganizationMember

# CommentPermissionDenied lives in apps.comments.policies (imported by
# services.py, not defined there), so it isn't a subclass of
# services.CommentServiceError — every mutating action needs both in its
# except clause. Mirrors apps.bugs.views' identical split.
_HANDLED_COMMENT_ERRORS = (services.CommentServiceError, CommentPermissionDenied)


def _detail_response(description: str) -> OpenApiResponse:
    return OpenApiResponse(
        response={"type": "object", "properties": {"detail": {"type": "string"}}},
        description=description,
    )


_FORBIDDEN_RESPONSE = _detail_response("The caller is authenticated but not permitted to do this.")
_NOT_FOUND_RESPONSE = _detail_response(
    "No bug or comment with this id exists in the caller's active organization."
)
_VALIDATION_ERROR_RESPONSE = OpenApiResponse(
    response={
        "type": "object",
        "additionalProperties": {"type": "array", "items": {"type": "string"}},
    },
    description="Structured per-field validation errors.",
)
_CONFLICT_RESPONSE = _detail_response(
    "The comment is not in a state that allows this action: it was already "
    "deleted/redacted, the edit window has passed, or the bug/project is archived."
)

# Maps a domain exception to the (status, body) the view returns — every
# exception apps.comments.services can raise is listed here exactly once, so
# each call site does `except _HANDLED_COMMENT_ERRORS as exc: return
# self.handle_comment_service_error(exc)` instead of its own except chain.
_ERROR_RESPONSES: dict[type[Exception], tuple[int, dict]] = {
    services.BugArchived: (
        status.HTTP_409_CONFLICT,
        {"detail": "This bug is archived. Comments cannot be added or changed."},
    ),
    services.ProjectArchived: (
        status.HTTP_409_CONFLICT,
        {"detail": "This bug's project is archived. Comments cannot be added or changed."},
    ),
    services.InvalidCommentBody: (
        status.HTTP_400_BAD_REQUEST,
        {"body": ["Comment body must be 1-10,000 characters after trimming."]},
    ),
    services.CommentNotActive: (
        status.HTTP_409_CONFLICT,
        {"detail": "This comment has already been deleted or redacted."},
    ),
    services.EditWindowExpired: (
        status.HTTP_409_CONFLICT,
        {"detail": "The edit window for this comment has passed."},
    ),
    CommentPermissionDenied: (
        status.HTTP_403_FORBIDDEN,
        {"detail": "You do not have permission to perform this action."},
    ),
}


class CommentErrorHandlingMixin:
    def _comment_context(self, request) -> dict:
        return {"request": request, "membership": getattr(request, "membership", None)}

    def handle_comment_service_error(self, exc: Exception) -> Response:
        for exc_type, (code, body) in _ERROR_RESPONSES.items():
            if isinstance(exc, exc_type):
                return Response(body, status=code)
        raise exc

    def _get_bug(self, request, bug_id):
        return get_object_or_404(get_bug_for_organization(request.organization), pk=bug_id)

    def _get_comment(self, bug, comment_id):
        return get_object_or_404(selectors.get_comment_for_bug(bug), pk=comment_id)

    def _serialize(self, comment, request) -> dict:
        return CommentSerializer(comment, context=self._comment_context(request)).data


class CommentListCreateView(CommentErrorHandlingMixin, APIView):
    """List/create comments on a bug. Open to any org member for GET (matching
    bug list/detail/activity); POST is fine-grained-gated inside
    apps.comments.services.create_comment (policies.can_comment), the same
    split apps.bugs.views uses for bug creation."""

    permission_classes = [IsOrganizationMember]

    @extend_schema(
        responses={
            200: CommentSerializer(many=True),
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
        }
    )
    def get(self, request, bug_id=None):
        bug = self._get_bug(request, bug_id)
        queryset = selectors.list_comments_for_bug(bug)

        paginator = BoundedPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = CommentSerializer(page, many=True, context=self._comment_context(request))
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=CommentCreateSerializer,
        responses={
            201: CommentSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    def post(self, request, bug_id=None):
        bug = self._get_bug(request, bug_id)
        serializer = CommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            comment = services.create_comment(
                bug=bug,
                author=request.user,
                membership=request.membership,
                body=serializer.validated_data["body"],
            )
        except _HANDLED_COMMENT_ERRORS as exc:
            return self.handle_comment_service_error(exc)
        return Response(self._serialize(comment, request), status=status.HTTP_201_CREATED)


class CommentDetailView(CommentErrorHandlingMixin, APIView):
    """Edit (PATCH) or remove (DELETE) a single comment. DELETE is a soft,
    non-enumerating removal — it returns 200 with the now-deleted comment's
    representation (thread placeholder), not 204, matching
    apps.bugs.views.BugTagDetailView's own DELETE-returns-the-resource style."""

    permission_classes = [IsOrganizationMember]

    @extend_schema(
        request=CommentUpdateSerializer,
        responses={
            200: CommentSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    def patch(self, request, bug_id=None, comment_id=None):
        bug = self._get_bug(request, bug_id)
        comment = self._get_comment(bug, comment_id)
        serializer = CommentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            comment = services.edit_comment(
                bug=bug,
                comment=comment,
                actor=request.user,
                membership=request.membership,
                body=serializer.validated_data["body"],
            )
        except _HANDLED_COMMENT_ERRORS as exc:
            return self.handle_comment_service_error(exc)
        return Response(self._serialize(comment, request))

    @extend_schema(
        request=None,
        responses={
            200: CommentSerializer,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    def delete(self, request, bug_id=None, comment_id=None):
        bug = self._get_bug(request, bug_id)
        comment = self._get_comment(bug, comment_id)

        try:
            comment = services.delete_comment(
                bug=bug, comment=comment, actor=request.user, membership=request.membership
            )
        except _HANDLED_COMMENT_ERRORS as exc:
            return self.handle_comment_service_error(exc)
        return Response(self._serialize(comment, request))


class CommentRedactView(CommentErrorHandlingMixin, APIView):
    """Administrator-only moderation action, distinct from DELETE — see
    apps.comments.services.redact_comment for why redact and delete are kept
    as separate, distinguishable terminal states."""

    permission_classes = [IsOrganizationMember]

    @extend_schema(
        request=None,
        responses={
            200: CommentSerializer,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    def post(self, request, bug_id=None, comment_id=None):
        bug = self._get_bug(request, bug_id)
        comment = self._get_comment(bug, comment_id)

        try:
            comment = services.redact_comment(
                bug=bug, comment=comment, actor=request.user, membership=request.membership
            )
        except _HANDLED_COMMENT_ERRORS as exc:
            return self.handle_comment_service_error(exc)
        return Response(self._serialize(comment, request))
