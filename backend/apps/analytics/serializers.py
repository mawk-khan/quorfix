from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.activities.models import ActivityVerb
from apps.bugs.models import BugPriority, BugSeverity, BugStatus
from apps.bugs.serializers import ProjectRefSerializer
from apps.projects.models import ProjectStatus
from apps.projects.selectors import get_projects_for_organization

# One inclusive-day span past this is rejected — see validate() below.
# Justified in the Phase 5 plan: daily-bucketed trend queries stay cheap at
# 366 buckets, and a longer window pushes into Professional's historical
# reporting territory rather than an operational dashboard.
MAX_RANGE_DAYS = 366


# -- query (request) serializers ---------------------------------------------


class ProjectFilterQuerySerializer(serializers.Serializer):
    """Shared base: the optional project filter, validated against the
    caller's own organization. `context["organization"]` is always set by
    the view from request.organization — never trusted from the request
    itself, so a foreign-org project id is rejected as a plain validation
    error rather than confirming or denying its existence elsewhere."""

    project = serializers.UUIDField(required=False)

    def validate_project(self, value):
        organization = self.context["organization"]
        if not get_projects_for_organization(organization).filter(pk=value).exists():
            raise serializers.ValidationError(
                "No project with this id exists in your organization."
            )
        return value


class DateRangeQuerySerializer(ProjectFilterQuerySerializer):
    """Adds the required date range — only used by the three endpoints whose
    metrics are actually range-scoped (summary's new/resolved, trends,
    resolution-time). Endpoints whose metrics are point-in-time snapshots
    use ProjectFilterQuerySerializer directly instead of forcing meaningless
    date parameters on them."""

    date_from = serializers.DateField()
    date_to = serializers.DateField()

    def validate(self, attrs):
        date_from = attrs["date_from"]
        date_to = attrs["date_to"]
        if date_to < date_from:
            raise serializers.ValidationError(
                {"date_to": ["date_to must not be before date_from."]}
            )
        if (date_to - date_from).days > MAX_RANGE_DAYS - 1:
            raise serializers.ValidationError(
                {"date_to": [f"Custom date ranges are limited to {MAX_RANGE_DAYS} days."]}
            )
        return attrs


# -- response serializers ------------------------------------------------


class SummaryResponseSerializer(serializers.Serializer):
    open_bugs = serializers.IntegerField()
    overdue_bugs = serializers.IntegerField()
    new_bugs = serializers.IntegerField()
    resolved_bugs = serializers.IntegerField()


class TrendPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    created = serializers.IntegerField()
    resolved = serializers.IntegerField()


class ResolutionTimeEntrySerializer(serializers.Serializer):
    priority = serializers.ChoiceField(choices=BugPriority.choices)
    average_seconds = serializers.IntegerField(
        allow_null=True,
        help_text="Null means no bug at this priority currently has a resolution in range — "
        "not zero seconds.",
    )


class StatusCountSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=BugStatus.choices)
    count = serializers.IntegerField()


class SeverityCountSerializer(serializers.Serializer):
    severity = serializers.ChoiceField(choices=BugSeverity.choices)
    count = serializers.IntegerField()


class DistributionsResponseSerializer(serializers.Serializer):
    status = StatusCountSerializer(many=True)
    severity = SeverityCountSerializer(many=True)


class WorkloadEntrySerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    name = serializers.CharField()
    role = serializers.CharField()
    count = serializers.IntegerField()


class WorkloadResponseSerializer(serializers.Serializer):
    eligible = WorkloadEntrySerializer(many=True)
    unassigned = serializers.IntegerField()
    needs_reassignment = WorkloadEntrySerializer(many=True)


class ActiveProjectSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    key = serializers.CharField()
    name = serializers.CharField()
    status = serializers.ChoiceField(choices=ProjectStatus.choices)
    total_bugs = serializers.IntegerField()
    open_bugs = serializers.IntegerField()


class DashboardActivityBugSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    key = serializers.CharField()
    title = serializers.CharField()


class DashboardActivitySerializer(serializers.Serializer):
    """Cross-bug activity feed row for the dashboard. Deliberately omits the
    raw `metadata` JSON field entirely — verb + from_value/to_value already
    carry everything needed for a human-readable summary line, so there's no
    per-verb allowlist to define or maintain, and nothing in metadata (e.g.
    attachment filenames) becomes a new exposure on this org-wide feed."""

    id = serializers.UUIDField()
    bug = DashboardActivityBugSerializer()
    project = ProjectRefSerializer(source="bug.project")
    actor = UserSerializer(allow_null=True)
    verb = serializers.ChoiceField(choices=ActivityVerb.choices)
    from_value = serializers.CharField()
    to_value = serializers.CharField()
    created_at = serializers.DateTimeField()
