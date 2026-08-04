import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.organizations.models import CommunityRole, Organization, OrganizationMembership

User = get_user_model()

DEFAULT_PASSWORD = "Str0ngPassw0rd!"


@pytest.fixture
def password():
    return DEFAULT_PASSWORD


@pytest.fixture
def make_user(db):
    def _make(email, password=DEFAULT_PASSWORD, **kwargs):
        import uuid

        return User.objects.create_user(
            username=uuid.uuid4().hex, email=email.lower(), password=password, **kwargs
        )

    return _make


@pytest.fixture
def organization(db):
    return Organization.objects.create(name="Acme", slug="acme")


@pytest.fixture
def make_membership(db):
    def _make(organization, user, role=CommunityRole.ADMINISTRATOR):
        return OrganizationMembership.objects.create(
            organization=organization, user=user, role=role, joined_at=timezone.now()
        )

    return _make


@pytest.fixture
def admin_user(make_user):
    return make_user("admin@example.com")


@pytest.fixture
def admin_membership(organization, admin_user, make_membership):
    return make_membership(organization, admin_user, role=CommunityRole.ADMINISTRATOR)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_client(api_client, admin_user, admin_membership):
    """Authenticated via a real session (force_login), not force_authenticate.

    force_authenticate bypasses DRF's authentication classes entirely, which
    means OrganizationAwareSessionAuthentication.authenticate() never runs
    and request.organization/request.membership never get set. force_login
    creates a real session so every request still goes through the normal
    authentication pipeline.
    """
    api_client.force_login(admin_user)
    return api_client
