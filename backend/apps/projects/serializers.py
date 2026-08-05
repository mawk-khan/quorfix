from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.projects.models import Project, project_key_validator
from apps.projects.selectors import is_eligible_project_lead, project_key_exists
from apps.projects.services import normalize_project_key

User = get_user_model()

PROJECT_DUPLICATE_KEY_MESSAGE = "A project with this key already exists in this organization."


class ProjectSerializer(serializers.ModelSerializer):
    lead = UserSerializer(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "key",
            "description",
            "status",
            "lead",
            "archived_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class _ProjectWriteSerializer(serializers.ModelSerializer):
    """Shared lead validation for create and update.

    `organization` is always read from the view's request context, never
    from the payload, and is what scopes both the key-uniqueness and
    lead-eligibility checks below.
    """

    lead = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True
    )

    def validate_lead(self, value):
        if value is None:
            return value
        organization = self.context["organization"]
        if not is_eligible_project_lead(organization, value.pk):
            raise serializers.ValidationError(
                "The project lead must be a current member of this organization."
            )
        return value


class ProjectCreateSerializer(_ProjectWriteSerializer):
    # Declared explicitly (not left to ModelSerializer's auto-generation) so
    # the model's project_key_validator isn't run on the raw, pre-normalized
    # input — validate_key below normalizes first, then applies that same
    # validator to the normalized value.
    key = serializers.CharField(max_length=10)

    class Meta:
        model = Project
        fields = ["name", "key", "description", "status", "lead"]

    def validate_key(self, value):
        normalized = normalize_project_key(value)
        project_key_validator(normalized)
        organization = self.context["organization"]
        if project_key_exists(organization, normalized):
            raise serializers.ValidationError(PROJECT_DUPLICATE_KEY_MESSAGE)
        return normalized


class ProjectUpdateSerializer(_ProjectWriteSerializer):
    """Excludes `key` entirely — project keys are immutable after creation
    so history, integrations, and exported URLs stay consistent."""

    class Meta:
        model = Project
        fields = ["name", "description", "status", "lead"]


class ProjectListQuerySerializer(serializers.Serializer):
    archived = serializers.ChoiceField(
        choices=["true", "false", "all"], required=False, default="false"
    )
    search = serializers.CharField(required=False, allow_blank=True, default="")
