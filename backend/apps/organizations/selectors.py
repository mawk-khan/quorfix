from django.db.models import QuerySet

from apps.organizations.models import Invitation, OrganizationMembership


def get_membership_for_user(user) -> OrganizationMembership | None:
    return OrganizationMembership.objects.select_related("organization").filter(user=user).first()


def get_organization_members(organization) -> QuerySet[OrganizationMembership]:
    return (
        OrganizationMembership.objects.select_related("user")
        .filter(organization=organization)
        .order_by("joined_at")
    )


def get_pending_invitations(organization) -> QuerySet[Invitation]:
    return (
        Invitation.objects.filter(
            organization=organization, accepted_at__isnull=True, revoked_at__isnull=True
        )
        .select_related("invited_by")
        .order_by("-created_at")
    )
