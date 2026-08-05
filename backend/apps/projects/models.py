from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Upper

from apps.core.models import OrganizationScopedModel

project_key_validator = RegexValidator(
    regex=r"^[A-Z][A-Z0-9]{1,9}$",
    message="Project key must be 2-10 characters, start with a letter, and contain only "
    "uppercase letters and digits.",
)


class ProjectStatus(models.TextChoices):
    PLANNING = "planning", "Planning"
    ACTIVE = "active", "Active"
    ON_HOLD = "on_hold", "On hold"
    COMPLETED = "completed", "Completed"


class Project(OrganizationScopedModel):
    name = models.CharField(max_length=255)
    key = models.CharField(max_length=10, validators=[project_key_validator])
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.ACTIVE
    )
    lead = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_projects",
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    next_bug_number = models.PositiveIntegerField(
        default=1,
        help_text="Next sequential number to assign within this project. Incremented under a "
        "row lock (select_for_update) inside apps.bugs.services.create_bug — never read or "
        "written anywhere else, so that transaction is the only place this can race.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "key"], name="unique_project_key_per_org"
            ),
            models.CheckConstraint(condition=Q(key=Upper("key")), name="project_key_is_uppercase"),
        ]
        indexes = [
            models.Index(fields=["organization", "archived_at"]),
            models.Index(fields=["organization", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.key} - {self.name}"
