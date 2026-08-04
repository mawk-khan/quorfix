from rest_framework.permissions import BasePermission

from apps.organizations.models import CommunityRole


class IsOrganizationMember(BasePermission):
    def has_permission(self, request, view) -> bool:
        return getattr(request, "organization", None) is not None


class IsOrganizationAdministrator(BasePermission):
    def has_permission(self, request, view) -> bool:
        membership = getattr(request, "membership", None)
        return membership is not None and membership.role == CommunityRole.ADMINISTRATOR
