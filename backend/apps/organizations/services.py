import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.organizations.models import (
    CommunityRole,
    Invitation,
    Organization,
    OrganizationMembership,
    SetupLock,
)
from apps.organizations.policies import OrganizationPolicy

User = get_user_model()


class SetupAlreadyCompleted(Exception):
    pass


class SetupNotAllowed(Exception):
    pass


class LastAdministratorError(Exception):
    pass


class InvitationAlreadyPending(Exception):
    pass


class MemberAlreadyExists(Exception):
    pass


class InvitationInvalid(Exception):
    pass


def is_instance_configured() -> bool:
    return SetupLock.objects.filter(id=1, completed_at__isnull=False).exists()


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _unique_slug(name: str) -> str:
    base = slugify(name) or "organization"
    slug = base
    suffix = 1
    while Organization.objects.filter(slug=slug).exists():
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


@transaction.atomic
def setup_instance(
    *, organization_name: str, email: str, password: str, first_name: str = "", last_name: str = ""
):
    """Creates the first admin + organization. Race-safe via SetupLock.

    select_for_update() needs an existing row to lock, and before any
    Organization exists there is none — hence the singleton SetupLock row
    (seeded by a migration), locked here before anything else happens.
    """
    lock = SetupLock.objects.select_for_update().get(id=1)
    if lock.completed_at is not None:
        raise SetupAlreadyCompleted()
    if not OrganizationPolicy.can_create_additional_organization():
        raise SetupNotAllowed()

    user = User.objects.create_user(
        username=uuid.uuid4().hex,
        email=email.lower(),
        password=password,
        first_name=first_name,
        last_name=last_name,
    )
    organization = Organization.objects.create(
        name=organization_name,
        slug=_unique_slug(organization_name),
    )
    membership = OrganizationMembership.objects.create(
        organization=organization,
        user=user,
        role=CommunityRole.ADMINISTRATOR,
        joined_at=timezone.now(),
    )
    lock.completed_at = timezone.now()
    lock.save(update_fields=["completed_at"])
    return user, organization, membership


@transaction.atomic
def create_invitation(
    *, organization: Organization, invited_by, email: str, role: str
) -> tuple[Invitation, str]:
    email = email.lower()

    if OrganizationMembership.objects.filter(organization=organization, user__email=email).exists():
        raise MemberAlreadyExists()

    existing = (
        Invitation.objects.select_for_update()
        .filter(
            organization=organization,
            email=email,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
        )
        .first()
    )
    if existing:
        if not existing.is_expired:
            raise InvitationAlreadyPending()
        # An expired-but-never-revoked invitation still satisfies the
        # partial unique constraint; revoke it so a fresh one can be created.
        existing.revoked_at = timezone.now()
        existing.save(update_fields=["revoked_at"])

    raw_token = secrets.token_urlsafe(32)
    invitation = Invitation.objects.create(
        organization=organization,
        email=email,
        role=role,
        token_hash=_hash_token(raw_token),
        invited_by=invited_by,
        expires_at=timezone.now() + timedelta(days=settings.INVITATION_EXPIRY_DAYS),
    )
    return invitation, raw_token


def get_invitation_by_token(raw_token: str) -> Invitation | None:
    return (
        Invitation.objects.select_related("organization")
        .filter(token_hash=_hash_token(raw_token))
        .first()
    )


@transaction.atomic
def accept_invitation(*, raw_token: str, password: str, first_name: str = "", last_name: str = ""):
    token_hash = _hash_token(raw_token)
    try:
        invitation = (
            Invitation.objects.select_for_update()
            .select_related("organization")
            .get(token_hash=token_hash)
        )
    except Invitation.DoesNotExist as exc:
        raise InvitationInvalid() from exc

    invitation_closed = invitation.accepted_at is not None or invitation.revoked_at is not None
    if invitation_closed or invitation.is_expired:
        raise InvitationInvalid()

    user, created = User.objects.get_or_create(
        email=invitation.email,
        defaults={
            "username": uuid.uuid4().hex,
            "first_name": first_name,
            "last_name": last_name,
        },
    )
    if created:
        user.set_password(password)
        user.save(update_fields=["password"])

    membership, _ = OrganizationMembership.objects.get_or_create(
        organization=invitation.organization,
        user=user,
        defaults={
            "role": invitation.role,
            "invited_by": invitation.invited_by,
            "joined_at": timezone.now(),
        },
    )

    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at"])
    return user, membership


@transaction.atomic
def revoke_invitation(*, invitation: Invitation) -> None:
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at"])


def _lock_organization_memberships(organization_id) -> list[OrganizationMembership]:
    """Locks every membership row for the org in a single FOR UPDATE query.

    A prior version split this into select_for_update().get(pk=...) followed
    by a separate .count() to check remaining admins — but Postgres doesn't
    apply FOR UPDATE to aggregate queries, so that .count() ran as an
    ordinary read that didn't wait for a concurrent transaction, letting two
    concurrent demotions both see "one other admin remains" and both
    proceed. Locking the whole set in one SELECT closes that race.
    """
    return list(
        OrganizationMembership.objects.select_for_update().filter(organization=organization_id)
    )


def _remaining_administrators(memberships: list[OrganizationMembership], excluding_pk) -> int:
    return sum(
        1
        for m in memberships
        if m.role == CommunityRole.ADMINISTRATOR and m.pk != excluding_pk
    )


@transaction.atomic
def change_member_role(
    *, membership: OrganizationMembership, new_role: str
) -> OrganizationMembership:
    org_memberships = _lock_organization_memberships(membership.organization_id)
    membership = next(m for m in org_memberships if m.pk == membership.pk)
    if membership.role == CommunityRole.ADMINISTRATOR and new_role != CommunityRole.ADMINISTRATOR:
        if _remaining_administrators(org_memberships, excluding_pk=membership.pk) == 0:
            raise LastAdministratorError()
    membership.role = new_role
    membership.save(update_fields=["role"])
    return membership


@transaction.atomic
def remove_member(*, membership: OrganizationMembership) -> None:
    org_memberships = _lock_organization_memberships(membership.organization_id)
    membership = next(m for m in org_memberships if m.pk == membership.pk)
    if membership.role == CommunityRole.ADMINISTRATOR:
        if _remaining_administrators(org_memberships, excluding_pk=membership.pk) == 0:
            raise LastAdministratorError()
    membership.delete()
