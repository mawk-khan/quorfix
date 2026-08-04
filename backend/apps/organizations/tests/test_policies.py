import pytest

from apps.core.registries import capability_registry
from apps.organizations.policies import OrganizationPolicy


@pytest.mark.django_db
def test_blocks_a_second_organization_without_the_capability(organization):
    assert not capability_registry.is_registered("multiple_organizations")
    assert OrganizationPolicy.can_create_additional_organization() is False


@pytest.mark.django_db
def test_allows_no_organization_yet(db):
    assert OrganizationPolicy.can_create_additional_organization() is True


@pytest.mark.django_db
def test_capability_registration_lifts_the_restriction(organization):
    """Proves the extension point actually works, using a fake provider —
    without needing a real Professional module installed."""
    assert OrganizationPolicy.can_create_additional_organization() is False

    capability_registry.register("multiple_organizations", object())
    try:
        assert OrganizationPolicy.can_create_additional_organization() is True
    finally:
        # The registry is a module-level singleton shared across the whole
        # test session — must unregister or later tests see this leak.
        capability_registry.unregister("multiple_organizations")

    assert OrganizationPolicy.can_create_additional_organization() is False
