from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.organizations.models import CommunityRole, Invitation, OrganizationMembership


@pytest.mark.django_db
def test_membership_is_unique_per_organization_and_user(organization, admin_user, admin_membership):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            OrganizationMembership.objects.create(
                organization=organization,
                user=admin_user,
                role=CommunityRole.VIEWER,
                joined_at=timezone.now(),
            )


@pytest.mark.django_db
def test_pending_invitation_is_unique_per_organization_and_email(organization, admin_user):
    Invitation.objects.create(
        organization=organization,
        email="new@example.com",
        role=CommunityRole.DEVELOPER,
        token_hash="a" * 64,
        invited_by=admin_user,
        expires_at=timezone.now() + timedelta(days=7),
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Invitation.objects.create(
                organization=organization,
                email="new@example.com",
                role=CommunityRole.VIEWER,
                token_hash="b" * 64,
                invited_by=admin_user,
                expires_at=timezone.now() + timedelta(days=7),
            )


@pytest.mark.django_db
def test_accepted_invitation_does_not_block_a_new_invitation_for_the_same_email(
    organization, admin_user
):
    """The partial unique constraint only applies while accepted_at/revoked_at
    are null — an accepted (or revoked) invitation must not block re-inviting
    that email later."""
    Invitation.objects.create(
        organization=organization,
        email="new@example.com",
        role=CommunityRole.DEVELOPER,
        token_hash="a" * 64,
        invited_by=admin_user,
        expires_at=timezone.now() + timedelta(days=7),
        accepted_at=timezone.now(),
    )
    Invitation.objects.create(
        organization=organization,
        email="new@example.com",
        role=CommunityRole.VIEWER,
        token_hash="b" * 64,
        invited_by=admin_user,
        expires_at=timezone.now() + timedelta(days=7),
    )


@pytest.mark.django_db
def test_invitation_is_expired_and_is_pending(organization, admin_user):
    expired = Invitation.objects.create(
        organization=organization,
        email="expired@example.com",
        role=CommunityRole.VIEWER,
        token_hash="c" * 64,
        invited_by=admin_user,
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    pending = Invitation.objects.create(
        organization=organization,
        email="pending@example.com",
        role=CommunityRole.VIEWER,
        token_hash="d" * 64,
        invited_by=admin_user,
        expires_at=timezone.now() + timedelta(days=7),
    )

    assert expired.is_expired is True
    assert expired.is_pending is False
    assert pending.is_expired is False
    assert pending.is_pending is True
