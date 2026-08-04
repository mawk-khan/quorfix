from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import BaseModel, OrganizationScopedModel


class CommunityRole(models.TextChoices):
    ADMINISTRATOR = "administrator", "Administrator"
    DEVELOPER = "developer", "Developer"
    QA = "qa", "QA"
    REPORTER = "reporter", "Reporter"
    VIEWER = "viewer", "Viewer"


class Organization(BaseModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class OrganizationMembership(OrganizationScopedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=CommunityRole.choices)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships_invited",
    )
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"], name="unique_membership_per_org"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "role"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.organization_id} ({self.role})"


class Invitation(OrganizationScopedModel):
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=CommunityRole.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations_sent",
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "email"],
                condition=Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="unique_pending_invitation_per_email",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "email"]),
        ]

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_pending(self) -> bool:
        return self.accepted_at is None and self.revoked_at is None and not self.is_expired

    def __str__(self) -> str:
        return f"{self.email} -> {self.organization_id} ({self.role})"


class SetupLock(models.Model):
    """Singleton row locked during first-run setup to prevent a double-submit race.

    Seeded by a data migration; application code never creates or deletes it.
    """

    id = models.IntegerField(primary_key=True, default=1)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return "setup-lock"
