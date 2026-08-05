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
from rest_framework.viewsets import GenericViewSet

from apps.organizations.permissions import IsOrganizationAdministrator, IsOrganizationMember
from apps.projects.models import Project
from apps.projects.selectors import get_projects_for_organization, list_projects
from apps.projects.serializers import (
    PROJECT_DUPLICATE_KEY_MESSAGE,
    ProjectCreateSerializer,
    ProjectListQuerySerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
)
from apps.projects.services import (
    DuplicateProjectKey,
    ProjectAlreadyArchived,
    ProjectNotArchived,
    archive_project,
    create_project,
    restore_project,
    update_project,
)


def _detail_response(description: str) -> OpenApiResponse:
    return OpenApiResponse(
        response={"type": "object", "properties": {"detail": {"type": "string"}}},
        description=description,
    )


_VALIDATION_ERROR_RESPONSE = OpenApiResponse(
    response={
        "type": "object",
        "additionalProperties": {"type": "array", "items": {"type": "string"}},
    },
    description="Structured per-field validation errors.",
)
_FORBIDDEN_RESPONSE = _detail_response("The caller is authenticated but not an administrator.")
_NOT_FOUND_RESPONSE = _detail_response(
    "No project with this id exists in the caller's active organization."
)
_ARCHIVED_CONFLICT_RESPONSE = _detail_response(
    "The project is archived; restore it before editing."
)
_ALREADY_ARCHIVED_RESPONSE = _detail_response("The project is already archived.")
_NOT_ARCHIVED_RESPONSE = _detail_response("The project is not archived.")


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                "archived",
                OpenApiTypes.STR,
                enum=["true", "false", "all"],
                description=(
                    "Filter by archive state. 'false' (default) returns active "
                    "projects only; 'true' returns archived only; 'all' returns both "
                    "— archived projects remain readable to every organization member."
                ),
            ),
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                description="Case-insensitive, trimmed match against project name or key. "
                "An empty value is treated as no filter.",
            ),
        ],
        responses={
            200: ProjectSerializer(many=True),
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
        },
    ),
    create=extend_schema(
        request=ProjectCreateSerializer,
        responses={
            201: ProjectSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
        },
    ),
    retrieve=extend_schema(
        responses={200: ProjectSerializer, 403: _FORBIDDEN_RESPONSE, 404: _NOT_FOUND_RESPONSE},
    ),
    partial_update=extend_schema(
        request=ProjectUpdateSerializer,
        responses={
            200: ProjectSerializer,
            400: _VALIDATION_ERROR_RESPONSE,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _ARCHIVED_CONFLICT_RESPONSE,
        },
    ),
)
class ProjectViewSet(GenericViewSet):
    """List/retrieve is open to any org member; create/update/archive/restore
    are administrator-only, matching MembershipViewSet's pattern.

    `queryset`/`serializer_class` are declared only so drf-spectacular can
    introspect response and path-parameter types — every action resolves its
    actual queryset and serializer explicitly, always scoped to
    request.organization.
    """

    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsOrganizationMember()]
        return [IsOrganizationAdministrator()]

    def get_object(self):
        return get_object_or_404(
            get_projects_for_organization(self.request.organization), pk=self.kwargs["pk"]
        )

    def list(self, request):
        query = ProjectListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        projects = list_projects(
            request.organization,
            archived=query.validated_data["archived"],
            search=query.validated_data["search"],
        )
        page = self.paginate_queryset(projects)
        serializer = ProjectSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request):
        serializer = ProjectCreateSerializer(
            data=request.data, context={"organization": request.organization}
        )
        serializer.is_valid(raise_exception=True)

        try:
            project = create_project(organization=request.organization, **serializer.validated_data)
        except DuplicateProjectKey:
            return Response(
                {"key": [PROJECT_DUPLICATE_KEY_MESSAGE]}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        return Response(ProjectSerializer(self.get_object()).data)

    def partial_update(self, request, pk=None):
        project = self.get_object()
        # Checked before validating the payload: an archived project must
        # come back restored before any field can change, regardless of
        # whether the submitted fields would otherwise be valid.
        if project.archived_at is not None:
            return Response(
                {"detail": "This project is archived. Restore it before editing."},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = ProjectUpdateSerializer(
            data=request.data, partial=True, context={"organization": request.organization}
        )
        serializer.is_valid(raise_exception=True)
        project = update_project(project=project, **serializer.validated_data)
        return Response(ProjectSerializer(project).data)

    @extend_schema(
        request=None,
        responses={
            200: ProjectSerializer,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _ALREADY_ARCHIVED_RESPONSE,
        },
    )
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        try:
            project = archive_project(project=self.get_object())
        except ProjectAlreadyArchived:
            return Response(
                {"detail": "This project is already archived."}, status=status.HTTP_409_CONFLICT
            )
        return Response(ProjectSerializer(project).data)

    @extend_schema(
        request=None,
        responses={
            200: ProjectSerializer,
            403: _FORBIDDEN_RESPONSE,
            404: _NOT_FOUND_RESPONSE,
            409: _NOT_ARCHIVED_RESPONSE,
        },
    )
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        try:
            project = restore_project(project=self.get_object())
        except ProjectNotArchived:
            return Response(
                {"detail": "This project is not archived."}, status=status.HTTP_409_CONFLICT
            )
        return Response(ProjectSerializer(project).data)
