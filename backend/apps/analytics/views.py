from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics import selectors
from apps.analytics.caching import cache_or_compute
from apps.analytics.serializers import (
    ActiveProjectSerializer,
    DashboardActivitySerializer,
    DateRangeQuerySerializer,
    DistributionsResponseSerializer,
    ProjectFilterQuerySerializer,
    ResolutionTimeEntrySerializer,
    SummaryResponseSerializer,
    TrendPointSerializer,
    WorkloadResponseSerializer,
)
from apps.organizations.permissions import IsOrganizationMember

# -- shared helpers -----------------------------------------------------


def _project_id(data: dict) -> str | None:
    project = data.get("project")
    return str(project) if project else None


def _project_key_segment(data: dict) -> str:
    project = data.get("project")
    return str(project) if project else "all"


def _validate_date_range(request) -> dict:
    query = DateRangeQuerySerializer(
        data=request.query_params, context={"organization": request.organization}
    )
    query.is_valid(raise_exception=True)
    return query.validated_data


def _validate_project_only(request) -> dict:
    query = ProjectFilterQuerySerializer(
        data=request.query_params, context={"organization": request.organization}
    )
    query.is_valid(raise_exception=True)
    return query.validated_data


# -- summary --------------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        parameters=[DateRangeQuerySerializer],
        responses={200: SummaryResponseSerializer},
        description="Open/overdue are current snapshots (ignore the date range). "
        "New/resolved are scoped to date_from..date_to.",
    )
)
class SummaryView(APIView):
    permission_classes = [IsOrganizationMember]

    def get(self, request):
        data = _validate_date_range(request)
        project_id = _project_id(data)
        organization = request.organization
        date_from, date_to = data["date_from"], data["date_to"]

        key = (
            f"analytics:{organization.pk}:summary:{_project_key_segment(data)}:"
            f"{date_from}:{date_to}:v1"
        )

        def compute():
            return {
                "open_bugs": selectors.open_bug_count(organization, project_id=project_id),
                "overdue_bugs": selectors.overdue_bug_count(organization, project_id=project_id),
                "new_bugs": selectors.new_bug_count(
                    organization, project_id=project_id, date_from=date_from, date_to=date_to
                ),
                "resolved_bugs": selectors.resolved_bug_count(
                    organization, project_id=project_id, date_from=date_from, date_to=date_to
                ),
            }

        result = cache_or_compute(key, compute)
        return Response(SummaryResponseSerializer(result).data)


# -- trends -----------------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        parameters=[DateRangeQuerySerializer], responses={200: TrendPointSerializer(many=True)}
    )
)
class TrendsView(APIView):
    permission_classes = [IsOrganizationMember]

    def get(self, request):
        data = _validate_date_range(request)
        project_id = _project_id(data)
        organization = request.organization
        date_from, date_to = data["date_from"], data["date_to"]

        key = (
            f"analytics:{organization.pk}:trends:{_project_key_segment(data)}:"
            f"{date_from}:{date_to}:v1"
        )

        def compute():
            return selectors.trends(
                organization, project_id=project_id, date_from=date_from, date_to=date_to
            )

        result = cache_or_compute(key, compute)
        return Response(TrendPointSerializer(result, many=True).data)


# -- resolution time --------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        parameters=[DateRangeQuerySerializer],
        responses={200: ResolutionTimeEntrySerializer(many=True)},
    )
)
class ResolutionTimeView(APIView):
    permission_classes = [IsOrganizationMember]

    def get(self, request):
        data = _validate_date_range(request)
        project_id = _project_id(data)
        organization = request.organization
        date_from, date_to = data["date_from"], data["date_to"]

        key = (
            f"analytics:{organization.pk}:resolution-time:{_project_key_segment(data)}:"
            f"{date_from}:{date_to}:v1"
        )

        def compute():
            by_priority = selectors.resolution_time_by_priority(
                organization, project_id=project_id, date_from=date_from, date_to=date_to
            )
            return [
                {
                    "priority": priority,
                    "average_seconds": int(duration.total_seconds())
                    if duration is not None
                    else None,
                }
                for priority, duration in by_priority.items()
            ]

        result = cache_or_compute(key, compute)
        return Response(ResolutionTimeEntrySerializer(result, many=True).data)


# -- distributions ------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        parameters=[ProjectFilterQuerySerializer], responses={200: DistributionsResponseSerializer}
    )
)
class DistributionsView(APIView):
    """Current backlog distribution — ignores the date range entirely (see
    docs/ACCESS_AND_TESTING.md: point-in-time vs. date-ranged sections)."""

    permission_classes = [IsOrganizationMember]

    def get(self, request):
        data = _validate_project_only(request)
        project_id = _project_id(data)
        organization = request.organization

        key = f"analytics:{organization.pk}:distributions:{_project_key_segment(data)}:v1"

        def compute():
            status_counts = selectors.status_distribution(organization, project_id=project_id)
            severity_counts = selectors.severity_distribution(organization, project_id=project_id)
            return {
                "status": [{"status": s, "count": c} for s, c in status_counts.items()],
                "severity": [{"severity": s, "count": c} for s, c in severity_counts.items()],
            }

        result = cache_or_compute(key, compute)
        return Response(DistributionsResponseSerializer(result).data)


# -- workload -----------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        parameters=[ProjectFilterQuerySerializer], responses={200: WorkloadResponseSerializer}
    )
)
class WorkloadView(APIView):
    """Current open workload only — ignores the date range (see
    docs/ACCESS_AND_TESTING.md)."""

    permission_classes = [IsOrganizationMember]

    def get(self, request):
        data = _validate_project_only(request)
        project_id = _project_id(data)
        organization = request.organization

        key = f"analytics:{organization.pk}:workload:{_project_key_segment(data)}:v1"

        def compute():
            return selectors.workload(organization, project_id=project_id)

        result = cache_or_compute(key, compute)
        return Response(WorkloadResponseSerializer(result).data)


# -- active projects ----------------------------------------------------


@extend_schema_view(get=extend_schema(responses={200: ActiveProjectSerializer(many=True)}))
class ActiveProjectsView(APIView):
    """No filters at all — neither date range nor project (it IS the project
    list)."""

    permission_classes = [IsOrganizationMember]

    def get(self, request):
        organization = request.organization
        key = f"analytics:{organization.pk}:active-projects:v1"

        def compute():
            return list(
                selectors.active_projects(organization).values(
                    "id", "key", "name", "status", "total_bugs", "open_bugs"
                )
            )

        result = cache_or_compute(key, compute)
        return Response(ActiveProjectSerializer(result, many=True).data)


# -- recent activity ------------------------------------------------------


@extend_schema_view(
    get=extend_schema(
        parameters=[ProjectFilterQuerySerializer],
        responses={200: DashboardActivitySerializer(many=True)},
    )
)
class RecentActivityView(generics.ListAPIView):
    """Bounded/paginated, project-filterable, org-wide activity feed.
    Deliberately not cached — see apps.analytics.caching module docstring
    and the Phase 5 plan: pagination/filter-aware keys would be needed and
    this is already a single bounded, indexed query."""

    permission_classes = [IsOrganizationMember]
    serializer_class = DashboardActivitySerializer

    def get_queryset(self):
        data = _validate_project_only(self.request)
        return selectors.recent_activity(self.request.organization, project_id=_project_id(data))
