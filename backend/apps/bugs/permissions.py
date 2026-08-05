from rest_framework.permissions import BasePermission

from apps.bugs import policies


class IsOrganizationMember(BasePermission):
    """Duplicated from apps.organizations.permissions rather than imported:
    that class is fine to reuse directly (it's stateless and has no
    bugs-specific meaning), so views.py imports the organizations version
    instead of this one — kept here only as the natural home for
    CanCreateBug below, which does need bugs-specific state."""

    def has_permission(self, request, view) -> bool:
        return getattr(request, "organization", None) is not None


class CanCreateBug(BasePermission):
    """Coarse, role-only pre-check — apps.bugs.services.create_bug enforces
    the identical rule again (see apps.bugs.policies.can_create_bug), so a
    service call that somehow bypasses this permission class is still
    denied."""

    def has_permission(self, request, view) -> bool:
        return policies.can_create_bug(getattr(request, "membership", None))
