from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from apps.activities.selectors import list_bug_activity
from apps.bugs import selectors, services
from apps.bugs.models import Bug
from apps.bugs.permissions import CanCreateBug
from apps.bugs.policies import BugPermissionDenied
from apps.bugs.serializers import (
    BugActivitySerializer,
    BugAssignSerializer,
    BugCreateSerializer,
    BugDetailSerializer,
    BugListQuerySerializer,
    BugListSerializer,
    BugTransitionSerializer,
    BugUpdateSerializer,
    RelationshipCreateSerializer,
    TagAddSerializer,
    VersionOnlySerializer,
)
from apps.bugs.services import UNSET
from apps.organizations.permissions import IsOrganizationMember

# BugPermissionDenied lives in apps.bugs.policies (imported by services.py,
# not defined there), so it isn't a subclass of services.BugServiceError —
# every mutating action needs both in its except clause.
_HANDLED_BUG_ERRORS = (services.BugServiceError, BugPermissionDenied)

# -- error dispatch ----------------------------------------------------


def _detail_response(description: str) -> OpenApiResponse:
    return OpenApiResponse(
        response={"type": "object", "properties": {"detail": {"type": "string"}}},
        description=description,
    )


_FORBIDDEN_RESPONSE = _detail_response("The caller is authenticated but not permitted to do this.")
_NOT_FOUND_RESPONSE = _detail_response(
    "No bug with this id exists in the caller's active organization."
)
_CONFLICT_RESPONSE = OpenApiResponse(
    response={
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "detail": {"type": "string"},
            "bug": {"type": "object"},
        },
    },
    description="Either bug_version_conflict (the bug changed since it was last fetched — "
    "'bug' carries the current server state) or the bug/its project is archived.",
)
_VALIDATION_ERROR_RESPONSE = OpenApiResponse(
    response={
        "type": "object",
        "additionalProperties": {"type": "array", "items": {"type": "string"}},
    },
    description="Structured per-field validation errors.",
)

# Maps a domain exception to the (status, body) the view returns. Every
# exception apps.bugs.services can raise (aside from BugVersionConflict,
# handled separately below since its body needs the current bug state)
# is listed here exactly once, so each service call site just does
# `except _HANDLED_BUG_ERRORS as exc: return self.handle_bug_service_error(exc, request)`
# instead of repeating a per-call except chain.
_ERROR_RESPONSES: dict[type[Exception], tuple[int, dict]] = {
    services.BugArchived: (
        status.HTTP_409_CONFLICT,
        {"detail": "This bug is archived. Restore it before making changes."},
    ),
    services.ProjectArchivedForBugMutation: (
        status.HTTP_409_CONFLICT,
        {"detail": "This bug's project is archived. Restore the project before making changes."},
    ),
    services.ProjectArchivedForBugCreation: (
        status.HTTP_409_CONFLICT,
        {"detail": "This project is archived. Restore it before adding new bugs."},
    ),
    services.BugAlreadyArchived: (
        status.HTTP_409_CONFLICT,
        {"detail": "This bug is already archived."},
    ),
    services.BugNotArchived: (
        status.HTTP_409_CONFLICT,
        {"detail": "This bug is not archived."},
    ),
    services.IneligibleAssignee: (
        status.HTTP_400_BAD_REQUEST,
        {
            "assignee": [
                "This user is not an eligible assignee — must be an administrator, "
                "developer, or QA member of this organization."
            ]
        },
    ),
    services.AssigneeRequiredForTransition: (
        status.HTTP_400_BAD_REQUEST,
        {"status": ["This status requires the bug to have an assignee."]},
    ),
    services.InvalidTagName: (
        status.HTTP_400_BAD_REQUEST,
        {"name": ["Tag name must be 1-50 characters after trimming."]},
    ),
    services.InvalidWorkflowTransition: (
        status.HTTP_400_BAD_REQUEST,
        {"status": ["This status transition is not allowed from the bug's current status."]},
    ),
    services.DuplicateTargetRequired: (
        status.HTTP_400_BAD_REQUEST,
        {
            "duplicate_of": [
                "A duplicate_of target bug is required when transitioning to duplicate."
            ]
        },
    ),
    services.DuplicateTargetArchived: (
        status.HTTP_400_BAD_REQUEST,
        {"duplicate_of": ["The target bug is archived and cannot be used as a duplicate target."]},
    ),
    services.DuplicateCycleDetected: (
        status.HTTP_400_BAD_REQUEST,
        {"duplicate_of": ["This would create a duplicate cycle."]},
    ),
    services.DuplicateChainUnverifiable: (
        status.HTTP_400_BAD_REQUEST,
        {
            "duplicate_of": [
                "Could not verify this duplicate chain is safe to create "
                "(chain too long to traverse)."
            ]
        },
    ),
    services.InvalidRelationshipType: (
        status.HTTP_400_BAD_REQUEST,
        {
            "relationship_type": [
                "duplicate_of relationships can only be created by transitioning a bug's "
                "status to duplicate."
            ]
        },
    ),
    services.DuplicateBugRelationship: (
        status.HTTP_400_BAD_REQUEST,
        {"detail": "This relationship already exists."},
    ),
    services.SelfRelationshipNotAllowed: (
        status.HTTP_400_BAD_REQUEST,
        {"related_bug": ["A bug cannot be related to itself."]},
    ),
    services.RelatedBugNotFound: (
        status.HTTP_400_BAD_REQUEST,
        {"related_bug": ["No bug with this id exists in your organization."]},
    ),
    services.RelationshipNotFound: (
        status.HTTP_404_NOT_FOUND,
        {"detail": "No relationship with this id exists on this bug."},
    ),
    BugPermissionDenied: (
        status.HTTP_403_FORBIDDEN,
        {"detail": "You do not have permission to perform this action."},
    ),
}


class BugErrorHandlingMixin:
    def _bug_context(self, request) -> dict:
        return {"request": request, "membership": getattr(request, "membership", None)}

    def handle_bug_service_error(self, exc: Exception, request) -> Response:
        if isinstance(exc, services.BugVersionConflict):
            return Response(
                {
                    "code": "bug_version_conflict",
                    "detail": "This bug was changed by someone else since you last loaded it.",
                    "bug": BugDetailSerializer(exc.bug, context=self._bug_context(request)).data,
                },
                status=status.HTTP_409_CONFLICT,
            )
        for exc_type, (code, body) in _ERROR_RESPONSES.items():
            if isinstance(exc, exc_type):
                return Response(body, status=code)
        raise exc


# -- viewset -------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("project", OpenApiTypes.UUID, description="Filter by project id."),
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                description="Comma-separated list of statuses.",
            ),
            OpenApiParameter("priority", OpenApiTypes.STR),
            OpenApiParameter("severity", OpenApiTypes.STR),
            OpenApiParameter("assignee", OpenApiTypes.UUID),
            OpenApiParameter("reporter", OpenApiTypes.UUID),
            OpenApiParameter("category", OpenApiTypes.STR),
            OpenApiParameter("tags", OpenApiTypes.STR, description="Comma-separated tag names."),
            OpenApiParameter("created_after", OpenApiTypes.DATETIME),
            OpenApiParameter("created_before", OpenApiTypes.DATETIME),
            OpenApiParameter("updated_after", OpenApiTypes.DATETIME),
            OpenApiParameter("updated_before", OpenApiTypes.DATETIME),
            OpenApiParameter("due_after", OpenApiTypes.DATE),
            OpenApiParameter("due_before", OpenApiTypes.DATE),
            OpenApiParameter("overdue", OpenApiTypes.BOOL),
            OpenApiParameter("unassigned", OpenApiTypes.BOOL),
            OpenApiParameter("watched_by_me", OpenApiTypes.BOOL),
            OpenApiParameter("archived", OpenApiTypes.STR, enum=["true", "false", "all"]),
            OpenApiParameter("search", OpenApiTypes.STR, description="Matches key or title."),
            OpenApiParameter(
                "ordering",
                OpenApiTypes.STR,
                description="One of created_at, updated_at, due_date, number, priority, "
                "severity — prefix with '-' to reverse.",
            ),
        ],
        responses={200: BugListSerializer(many=True), 400: _VALIDATION_ERROR_RESPONSE},
    ),
    create=extend_schema(
        request=BugCreateSerializer,
        responses={
            201: BugDetailSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    ),
    retrieve=extend_schema(
        responses={200: BugDetailSerializer, 403: _FORBIDDEN_RESPONSE, 404: _NOT_FOUND_RESPONSE}
    ),
    partial_update=extend_schema(
        request=BugUpdateSerializer,
        responses={
            200: BugDetailSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    ),
)
class BugViewSet(BugErrorHandlingMixin, GenericViewSet):
    """List/retrieve/activity are open to any org member; create needs a
    create-eligible role; every other mutation is coarsely gated by
    IsOrganizationMember here and finely gated inside apps.bugs.services —
    see BugErrorHandlingMixin for how a resulting BugPermissionDenied (or
    any other domain exception) becomes the HTTP response.
    """

    queryset = Bug.objects.all()
    serializer_class = BugDetailSerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsOrganizationMember(), CanCreateBug()]
        return [IsOrganizationMember()]

    def get_object(self) -> Bug:
        return get_object_or_404(
            selectors.get_bug_for_organization(self.request.organization, viewer=self.request.user),
            pk=self.kwargs["pk"],
        )

    def _detail(self, bug: Bug, request) -> dict:
        return BugDetailSerializer(bug, context=self._bug_context(request)).data

    # -- list / create / retrieve / update ---------------------------------

    def list(self, request):
        query = BugListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data

        bugs = selectors.list_bugs(
            request.organization,
            viewer=request.user,
            project=str(data["project"]) if data.get("project") else None,
            statuses=data.get("status") or None,
            priority=data.get("priority"),
            severity=data.get("severity"),
            assignee=str(data["assignee"]) if data.get("assignee") else None,
            reporter=str(data["reporter"]) if data.get("reporter") else None,
            category=data.get("category") or None,
            tags=data.get("tags") or None,
            created_after=data.get("created_after"),
            created_before=data.get("created_before"),
            updated_after=data.get("updated_after"),
            updated_before=data.get("updated_before"),
            due_after=data.get("due_after"),
            due_before=data.get("due_before"),
            overdue=data.get("overdue", False),
            unassigned=data.get("unassigned", False),
            watched_by_me=data.get("watched_by_me", False),
            archived=data.get("archived", "false"),
            search=data.get("search"),
            ordering=data.get("ordering", "-created_at"),
        )
        page = self.paginate_queryset(bugs)
        serializer = BugListSerializer(page, many=True, context=self._bug_context(request))
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        serializer = BugCreateSerializer(
            data=request.data, context={"organization": request.organization}
        )
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        project = fields.pop("project")

        try:
            bug = services.create_bug(
                organization=request.organization,
                project=project,
                reporter=request.user,
                membership=request.membership,
                **fields,
            )
        except _HANDLED_BUG_ERRORS as exc:
            return self.handle_bug_service_error(exc, request)
        return Response(self._detail(bug, request), status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        return Response(self._detail(self.get_object(), request))

    def partial_update(self, request, pk=None):
        bug = self.get_object()
        serializer = BugUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        expected_version = fields.pop("version")

        try:
            bug = services.update_bug(
                bug=bug,
                actor=request.user,
                membership=request.membership,
                expected_version=expected_version,
                **fields,
            )
        except _HANDLED_BUG_ERRORS as exc:
            return self.handle_bug_service_error(exc, request)
        return Response(self._detail(bug, request))

    # -- workflow / assignment / archive ----------------------------------

    @extend_schema(
        request=BugTransitionSerializer,
        responses={
            200: BugDetailSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        bug = self.get_object()
        serializer = BugTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        assignee_id = data["assignee"] if "assignee" in data else UNSET
        if assignee_id not in (UNSET, None):
            assignee_id = str(assignee_id)

        try:
            bug = services.transition_bug(
                bug=bug,
                actor=request.user,
                membership=request.membership,
                new_status=data["status"],
                expected_version=data["version"],
                duplicate_of=str(data["duplicate_of"]) if data.get("duplicate_of") else None,
                assignee_id=assignee_id,
            )
        except _HANDLED_BUG_ERRORS as exc:
            return self.handle_bug_service_error(exc, request)
        return Response(self._detail(bug, request))

    @extend_schema(
        request=BugAssignSerializer,
        responses={
            200: BugDetailSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        bug = self.get_object()
        serializer = BugAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        assignee_id = str(data["assignee"]) if data["assignee"] else None

        try:
            bug = services.assign_bug(
                bug=bug,
                actor=request.user,
                membership=request.membership,
                assignee_id=assignee_id,
                expected_version=data["version"],
            )
        except _HANDLED_BUG_ERRORS as exc:
            return self.handle_bug_service_error(exc, request)
        return Response(self._detail(bug, request))

    @extend_schema(
        request=VersionOnlySerializer,
        responses={
            200: BugDetailSerializer,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        bug = self.get_object()
        serializer = VersionOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            bug = services.archive_bug(
                bug=bug,
                actor=request.user,
                membership=request.membership,
                expected_version=serializer.validated_data["version"],
            )
        except _HANDLED_BUG_ERRORS as exc:
            return self.handle_bug_service_error(exc, request)
        return Response(self._detail(bug, request))

    @extend_schema(
        request=VersionOnlySerializer,
        responses={
            200: BugDetailSerializer,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        bug = self.get_object()
        serializer = VersionOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            bug = services.restore_bug(
                bug=bug,
                actor=request.user,
                membership=request.membership,
                expected_version=serializer.validated_data["version"],
            )
        except _HANDLED_BUG_ERRORS as exc:
            return self.handle_bug_service_error(exc, request)
        return Response(self._detail(bug, request))

    # -- tags ----------------------------------------------------------

    @extend_schema(
        request=TagAddSerializer,
        responses={
            200: BugDetailSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    @action(detail=True, methods=["post"], url_path="tags")
    def add_tag(self, request, pk=None):
        bug = self.get_object()
        serializer = TagAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            bug = services.add_tag(
                bug=bug,
                actor=request.user,
                membership=request.membership,
                name=serializer.validated_data["name"],
                expected_version=serializer.validated_data["version"],
            )
        except _HANDLED_BUG_ERRORS as exc:
            return self.handle_bug_service_error(exc, request)
        return Response(self._detail(bug, request))

    # -- watch / unwatch (self-service, no version, no activity) ----------

    @extend_schema(
        request=None,
        responses={200: BugDetailSerializer, 403: _FORBIDDEN_RESPONSE, 404: _NOT_FOUND_RESPONSE},
    )
    @action(detail=True, methods=["post", "delete"], url_path="watch")
    def watch(self, request, pk=None):
        bug = self.get_object()
        if request.method == "POST":
            services.watch_bug(bug=bug, user=request.user)
            is_watching = True
        else:
            services.unwatch_bug(bug=bug, user=request.user)
            is_watching = False
        # get_object() annotated is_watching *before* this mutation, so
        # that cached value is now stale — overwrite it directly rather
        # than re-querying, since we already know the answer.
        bug.is_watching = is_watching
        return Response(self._detail(bug, request))

    # -- activity feed ---------------------------------------------------

    @extend_schema(
        responses={
            200: BugActivitySerializer(many=True),
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
        }
    )
    @action(detail=True, methods=["get"], url_path="activity")
    def activity(self, request, pk=None):
        bug = self.get_object()
        page = self.paginate_queryset(list_bug_activity(bug))
        serializer = BugActivitySerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    # -- relationships (create only; delete is BugRelationshipDetailView) --

    @extend_schema(
        request=RelationshipCreateSerializer,
        responses={
            201: BugDetailSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _CONFLICT_RESPONSE,
        },
    )
    @action(detail=True, methods=["post"], url_path="relationships")
    def add_relationship(self, request, pk=None):
        bug = self.get_object()
        serializer = RelationshipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            bug = services.create_relationship(
                bug=bug,
                actor=request.user,
                membership=request.membership,
                related_bug_id=str(data["related_bug"]),
                relationship_type=data["relationship_type"],
                expected_version=data["version"],
            )
        except _HANDLED_BUG_ERRORS as exc:
            return self.handle_bug_service_error(exc, request)
        return Response(self._detail(bug, request), status=status.HTTP_201_CREATED)


# -- nested resource-oriented DELETE routes --------------------------------
#
# DRF's @action only appends one path segment after the detail pk, so a
# genuinely nested "remove this specific child by id" route (tags/{tag_id},
# relationships/{relationship_id}) is wired as its own APIView + explicit
# path() in urls.py instead of forcing it through the router. This keeps
# the HTTP verb resource-oriented (DELETE, not POST .../remove/) as
# required, at the cost of living outside the ViewSet's action list.


@extend_schema(
    request=VersionOnlySerializer,
    responses={
        200: BugDetailSerializer,
        400: _VALIDATION_ERROR_RESPONSE,
        403: _FORBIDDEN_RESPONSE,
        404: _NOT_FOUND_RESPONSE,
        409: _CONFLICT_RESPONSE,
    },
)
class BugTagDetailView(BugErrorHandlingMixin, APIView):
    permission_classes = [IsOrganizationMember]

    def delete(self, request, pk=None, tag_id=None):
        bug = get_object_or_404(selectors.get_bugs_for_organization(request.organization), pk=pk)
        serializer = VersionOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            bug = services.remove_tag(
                bug=bug,
                actor=request.user,
                membership=request.membership,
                tag_id=tag_id,
                expected_version=serializer.validated_data["version"],
            )
        except _HANDLED_BUG_ERRORS as exc:
            return self.handle_bug_service_error(exc, request)
        return Response(BugDetailSerializer(bug, context=self._bug_context(request)).data)


@extend_schema(
    request=VersionOnlySerializer,
    responses={
        200: BugDetailSerializer,
        400: _VALIDATION_ERROR_RESPONSE,
        403: _FORBIDDEN_RESPONSE,
        404: _NOT_FOUND_RESPONSE,
        409: _CONFLICT_RESPONSE,
    },
)
class BugRelationshipDetailView(BugErrorHandlingMixin, APIView):
    permission_classes = [IsOrganizationMember]

    def delete(self, request, pk=None, relationship_id=None):
        bug = get_object_or_404(selectors.get_bugs_for_organization(request.organization), pk=pk)
        serializer = VersionOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            bug = services.remove_relationship(
                bug=bug,
                actor=request.user,
                membership=request.membership,
                relationship_id=relationship_id,
                expected_version=serializer.validated_data["version"],
            )
        except _HANDLED_BUG_ERRORS as exc:
            return self.handle_bug_service_error(exc, request)
        return Response(BugDetailSerializer(bug, context=self._bug_context(request)).data)
