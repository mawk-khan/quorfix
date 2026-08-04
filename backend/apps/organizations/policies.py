from apps.core.registries import capability_registry
from apps.organizations.models import Organization


class OrganizationPolicy:
    """Community/Professional boundary for the one-active-organization rule.

    Community exposes no generic "create organization" API, so in practice
    this only ever gates the one-time instance-setup call. The check lives
    here (not inline in the setup view) so a future Professional endpoint
    can consult the identical function once it registers the capability,
    without any schema change or edition check scattered elsewhere.
    """

    CAPABILITY = "multiple_organizations"

    @classmethod
    def can_create_additional_organization(cls) -> bool:
        if capability_registry.is_registered(cls.CAPABILITY):
            return True
        return not Organization.objects.filter(is_active=True).exists()
