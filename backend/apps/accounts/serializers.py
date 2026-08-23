from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.services import DEMO_ROLE_TO_EMAIL

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name"]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})


class DemoLoginSerializer(serializers.Serializer):
    # ChoiceField enforces the strict allow-list at validation time — an
    # unrecognized value is a plain 400, never reaching
    # apps.accounts.services.resolve_demo_login_user at all.
    role = serializers.ChoiceField(choices=list(DEMO_ROLE_TO_EMAIL.keys()))
