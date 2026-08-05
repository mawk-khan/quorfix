from django.conf import settings
from django.db import models

from apps.core.models import UUIDPrimaryKeyModel


class ActivityVerb(models.TextChoices):
    CREATED = "created", "Created"
    STATUS_CHANGED = "status_changed", "Status changed"
    ASSIGNED = "assigned", "Assigned"
    UNASSIGNED = "unassigned", "Unassigned"
    PRIORITY_CHANGED = "priority_changed", "Priority changed"
    SEVERITY_CHANGED = "severity_changed", "Severity changed"
    FIELD_UPDATED = "field_updated", "Field updated"
    TAG_ADDED = "tag_added", "Tag added"
    TAG_REMOVED = "tag_removed", "Tag removed"
    RELATIONSHIP_ADDED = "relationship_added", "Relationship added"
    RELATIONSHIP_REMOVED = "relationship_removed", "Relationship removed"
    ARCHIVED = "archived", "Archived"
    RESTORED = "restored", "Restored"


class BugActivity(UUIDPrimaryKeyModel):
    """Immutable, append-only record of a change to a bug.

    Deliberately not built on TimeStampedModel/OrganizationScopedModel:
    there is only `created_at`, no `updated_at`, and no view anywhere
    exposes an update or delete route for this model — immutability is
    structural here, not just a convention callers have to remember. Rows
    are only ever written through apps.activities.services, never edited.

    `organization` is a direct FK (not resolved via `bug.organization`) so
    every list/filter query here is a plain indexed filter, not a join.
    """

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    bug = models.ForeignKey("bugs.Bug", on_delete=models.CASCADE, related_name="activities")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Null means system-generated (e.g. membership removal clearing an assignment).",
    )
    verb = models.CharField(max_length=32, choices=ActivityVerb.choices)
    from_value = models.CharField(max_length=255, blank=True, default="")
    to_value = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "bug", "-created_at"]),
        ]
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.verb} on bug {self.bug_id}"
