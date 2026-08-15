from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.organizations.models import Invitation, Organization, OrganizationMembership


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug"]
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = ["id", "user", "role", "joined_at"]
        read_only_fields = ["id", "user", "joined_at"]


class MembershipRoleUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=OrganizationMembership._meta.get_field("role").choices)


class SessionSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    user = UserSerializer(allow_null=True)
    organization = OrganizationSerializer(allow_null=True)
    role = serializers.CharField(allow_null=True)
    demo_banner = serializers.CharField(allow_blank=True)


class InvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "invited_by", "created_at", "expires_at"]
        read_only_fields = fields


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=OrganizationMembership._meta.get_field("role").choices)


class InvitationPublicDetailSerializer(serializers.Serializer):
    organization_name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    expires_at = serializers.DateTimeField()


class InvitationAcceptSerializer(serializers.Serializer):
    password = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")


class SetupSerializer(serializers.Serializer):
    organization_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")
