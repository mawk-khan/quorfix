from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.bugs import policies, workflow
from apps.bugs.models import Bug, BugPriority, BugSeverity, BugStatus, RelationshipType, Tag
from apps.bugs.selectors import SORT_FIELDS, list_bug_relationships
from apps.projects.models import Project

User = get_user_model()

MAX_TAG_NAME_LENGTH = 50


class ProjectRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "key", "name"]
        read_only_fields = fields


class BugRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bug
        fields = ["id", "key", "title", "status"]
        read_only_fields = fields


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]
        read_only_fields = fields


class BugRelationshipViewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.CharField()
    bug = BugRefSerializer()


class _MembershipAwareSerializer(serializers.ModelSerializer):
    """Shared helper for reading the acting membership out of context —
    passed explicitly by the view rather than derived from request, so
    tests can exercise these serializers without a full request cycle."""

    def _membership(self):
        return self.context.get("membership")


class BugListSerializer(_MembershipAwareSerializer):
    """Deliberately lean: no description/steps/etc. and no tags/watchers/
    relationships collections, so a page of 25 rows stays a handful of
    small queries regardless of how much detail any one bug carries."""

    project = ProjectRefSerializer(read_only=True)
    reporter = UserSerializer(read_only=True)
    assignee = UserSerializer(read_only=True)
    is_watching = serializers.SerializerMethodField()

    class Meta:
        model = Bug
        fields = [
            "id",
            "key",
            "number",
            "project",
            "title",
            "status",
            "priority",
            "severity",
            "reporter",
            "assignee",
            "due_date",
            "archived_at",
            "version",
            "is_watching",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_is_watching(self, obj) -> bool:
        # Relies entirely on the Exists() annotation from
        # apps.bugs.selectors.list_bugs — never falls back to a query here,
        # since that would reintroduce one query per row.
        return bool(getattr(obj, "is_watching", False))


class BugDetailSerializer(_MembershipAwareSerializer):
    project = ProjectRefSerializer(read_only=True)
    reporter = UserSerializer(read_only=True)
    assignee = UserSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    is_watching = serializers.SerializerMethodField()
    watcher_count = serializers.SerializerMethodField()
    available_transitions = serializers.SerializerMethodField()
    editable_fields = serializers.SerializerMethodField()
    can_assign = serializers.SerializerMethodField()
    can_archive = serializers.SerializerMethodField()
    can_manage_relationships = serializers.SerializerMethodField()
    relationships = serializers.SerializerMethodField()

    class Meta:
        model = Bug
        fields = [
            "id",
            "key",
            "number",
            "project",
            "title",
            "description",
            "steps_to_reproduce",
            "expected_result",
            "actual_result",
            "environment",
            "category",
            "status",
            "priority",
            "severity",
            "reporter",
            "assignee",
            "due_date",
            "resolved_at",
            "closed_at",
            "archived_at",
            "version",
            "tags",
            "watcher_count",
            "is_watching",
            "available_transitions",
            "editable_fields",
            "can_assign",
            "can_archive",
            "can_manage_relationships",
            "relationships",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_is_watching(self, obj) -> bool:
        annotated = getattr(obj, "is_watching", None)
        if annotated is not None:
            return bool(annotated)
        request = self.context.get("request")
        if request is None or not getattr(request.user, "is_authenticated", False):
            return False
        return obj.watchers.filter(pk=request.user.pk).exists()

    def get_watcher_count(self, obj) -> int:
        return obj.watchers.count()

    def get_available_transitions(self, obj) -> list[str]:
        matrix = workflow.get_transition_matrix(obj.project)
        candidates = matrix.get(obj.status, frozenset())
        membership = self._membership()
        return sorted(t for t in candidates if policies.can_change_status(obj, membership, t))

    def get_editable_fields(self, obj) -> list[str]:
        return sorted(policies.editable_fields_for(obj, self._membership()))

    def get_can_assign(self, obj) -> bool:
        return policies.can_assign_bug(self._membership())

    def get_can_archive(self, obj) -> bool:
        return policies.can_archive_bug(self._membership())

    def get_can_manage_relationships(self, obj) -> bool:
        return policies.can_manage_relationships(self._membership())

    @extend_schema_field(BugRelationshipViewSerializer(many=True))
    def get_relationships(self, obj):
        return BugRelationshipViewSerializer(list_bug_relationships(obj), many=True).data


class BugCreateSerializer(serializers.Serializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    steps_to_reproduce = serializers.CharField(required=False, allow_blank=True, default="")
    expected_result = serializers.CharField(required=False, allow_blank=True, default="")
    actual_result = serializers.CharField(required=False, allow_blank=True, default="")
    environment = serializers.CharField(required=False, allow_blank=True, default="")
    category = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    priority = serializers.ChoiceField(
        choices=BugPriority.choices, required=False, default=BugPriority.MEDIUM
    )
    severity = serializers.ChoiceField(
        choices=BugSeverity.choices, required=False, default=BugSeverity.MAJOR
    )
    due_date = serializers.DateField(required=False, allow_null=True, default=None)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Title is required.")
        return value

    def validate_category(self, value):
        return value.strip()

    def validate_project(self, value):
        # Same message whether the id doesn't exist at all or belongs to
        # another organization — never reveal which.
        organization = self.context["organization"]
        if value.organization_id != organization.id:
            raise serializers.ValidationError(
                "No project with this id exists in your organization."
            )
        return value


class BugUpdateSerializer(serializers.Serializer):
    """Deliberately excludes status/assignee/reporter/project/key/number/
    version-as-a-content-field/resolved_at/closed_at/archived_at — those
    fields simply don't exist here, so PATCH can never touch them no matter
    what a client sends. `version` is present as the required optimistic-
    concurrency token, not as an editable field."""

    version = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    steps_to_reproduce = serializers.CharField(required=False, allow_blank=True)
    expected_result = serializers.CharField(required=False, allow_blank=True)
    actual_result = serializers.CharField(required=False, allow_blank=True)
    environment = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, allow_blank=True, max_length=100)
    due_date = serializers.DateField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=BugPriority.choices, required=False)
    severity = serializers.ChoiceField(choices=BugSeverity.choices, required=False)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Title cannot be blank.")
        return value

    def validate_category(self, value):
        return value.strip()


class BugTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=BugStatus.choices)
    version = serializers.IntegerField(min_value=1)
    duplicate_of = serializers.UUIDField(required=False)
    # Tri-state: absent means "leave assignee unchanged", present+null means
    # "unassign", present+value means "assign" — required=False so an
    # omitted key never lands in validated_data at all, which is exactly
    # the "not provided" signal the view checks for.
    assignee = serializers.UUIDField(required=False, allow_null=True)


class BugAssignSerializer(serializers.Serializer):
    assignee = serializers.UUIDField(allow_null=True)
    version = serializers.IntegerField(min_value=1)


class VersionOnlySerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


class TagAddSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=MAX_TAG_NAME_LENGTH)
    version = serializers.IntegerField(min_value=1)


class RelationshipCreateSerializer(serializers.Serializer):
    related_bug = serializers.UUIDField()
    relationship_type = serializers.ChoiceField(
        choices=[RelationshipType.BLOCKS, RelationshipType.RELATES_TO]
    )
    version = serializers.IntegerField(min_value=1)


class BugActivitySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    verb = serializers.CharField()
    actor = UserSerializer(allow_null=True)
    from_value = serializers.CharField()
    to_value = serializers.CharField()
    metadata = serializers.JSONField()
    created_at = serializers.DateTimeField()


class BugListQuerySerializer(serializers.Serializer):
    project = serializers.UUIDField(required=False)
    status = serializers.CharField(required=False, allow_blank=True, default="")
    priority = serializers.ChoiceField(choices=BugPriority.choices, required=False)
    severity = serializers.ChoiceField(choices=BugSeverity.choices, required=False)
    assignee = serializers.UUIDField(required=False)
    reporter = serializers.UUIDField(required=False)
    category = serializers.CharField(required=False, allow_blank=True, default="")
    tags = serializers.CharField(required=False, allow_blank=True, default="")
    created_after = serializers.DateTimeField(required=False)
    created_before = serializers.DateTimeField(required=False)
    updated_after = serializers.DateTimeField(required=False)
    updated_before = serializers.DateTimeField(required=False)
    due_after = serializers.DateField(required=False)
    due_before = serializers.DateField(required=False)
    overdue = serializers.BooleanField(required=False, default=False)
    unassigned = serializers.BooleanField(required=False, default=False)
    watched_by_me = serializers.BooleanField(required=False, default=False)
    archived = serializers.ChoiceField(
        choices=["true", "false", "all"], required=False, default="false"
    )
    search = serializers.CharField(required=False, allow_blank=True, default="")
    ordering = serializers.CharField(required=False, default="-created_at")

    def validate_status(self, value):
        if not value:
            return []
        values = [v.strip() for v in value.split(",") if v.strip()]
        invalid = [v for v in values if v not in BugStatus.values]
        if invalid:
            raise serializers.ValidationError(f"Invalid status value(s): {', '.join(invalid)}")
        return values

    def validate_tags(self, value):
        if not value:
            return []
        return [t.strip() for t in value.split(",") if t.strip()]

    def validate_category(self, value):
        return value.strip()

    def validate_ordering(self, value):
        field = value[1:] if value.startswith("-") else value
        if field not in SORT_FIELDS:
            raise serializers.ValidationError(f"Invalid ordering field: {field!r}")
        return value
