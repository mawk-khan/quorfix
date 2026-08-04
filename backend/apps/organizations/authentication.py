from rest_framework.authentication import SessionAuthentication

from apps.organizations.models import OrganizationMembership


class OrganizationAwareSessionAuthentication(SessionAuthentication):
    """SessionAuthentication that also resolves the caller's active organization.

    DRF accesses `request.user` (triggering authenticate()) during
    perform_authentication(), which always runs before check_permissions() —
    so `request.organization`/`request.membership` are set before any
    permission class reads them. For an anonymous request, authenticate()
    returns early and these attributes are never set at all: read them with
    `getattr(request, "organization", None)`, never directly.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user, _ = result
            membership = (
                OrganizationMembership.objects.select_related("organization")
                .filter(user=user)
                .first()
            )
            request.organization = membership.organization if membership else None
            request.membership = membership
        return result
