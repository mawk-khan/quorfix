from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import OrganizationScopedModel


class BugStatus(models.TextChoices):
    NEW = "new", "New"
    TRIAGED = "triaged", "Triaged"
    ASSIGNED = "assigned", "Assigned"
    IN_PROGRESS = "in_progress", "In progress"
    READY_FOR_QA = "ready_for_qa", "Ready for QA"
    RESOLVED = "resolved", "Resolved"
    REOPENED = "reopened", "Reopened"
    CLOSED = "closed", "Closed"
    BLOCKED = "blocked", "Blocked"
    DUPLICATE = "duplicate", "Duplicate"
    CANNOT_REPRODUCE = "cannot_reproduce", "Cannot reproduce"
    WONT_FIX = "wont_fix", "Won't fix"
    DEFERRED = "deferred", "Deferred"


class BugPriority(models.TextChoices):
    URGENT = "urgent", "Urgent"
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


class BugSeverity(models.TextChoices):
    BLOCKER = "blocker", "Blocker"
    CRITICAL = "critical", "Critical"
    MAJOR = "major", "Major"
    MINOR = "minor", "Minor"
    TRIVIAL = "trivial", "Trivial"


class RelationshipType(models.TextChoices):
    DUPLICATE_OF = "duplicate_of", "Duplicate of"
    BLOCKS = "blocks", "Blocks"
    RELATES_TO = "relates_to", "Relates to"


class Tag(OrganizationScopedModel):
    """Reusable, organization-scoped label.

    `name` preserves the casing the first creator used; `name_normalized`
    (trimmed, lowercased) is what uniqueness is actually enforced against —
    a plain UniqueConstraint on `name` would allow "Bug" and "bug" as two
    different tags in the same org, which the Phase 3 spec explicitly rules
    out. Set by apps.bugs.services, never left to the model to compute.
    """

    name = models.CharField(max_length=50)
    name_normalized = models.CharField(max_length=50, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name_normalized"], name="unique_tag_name_per_org_ci"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "name_normalized"]),
        ]

    def __str__(self) -> str:
        return self.name


class Bug(OrganizationScopedModel):
    # PROTECT, not CASCADE: bugs are audit-significant history and this app
    # exposes no project-delete endpoint at all (only archive/restore), so a
    # cascading delete here would only ever be an accident, never a real
    # user action to support.
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="bugs")
    number = models.PositiveIntegerField()
    key = models.CharField(max_length=20, editable=False)

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    steps_to_reproduce = models.TextField(blank=True, default="")
    expected_result = models.TextField(blank=True, default="")
    actual_result = models.TextField(blank=True, default="")
    environment = models.TextField(blank=True, default="")
    category = models.CharField(max_length=100, blank=True, default="")

    status = models.CharField(max_length=20, choices=BugStatus.choices, default=BugStatus.NEW)
    priority = models.CharField(
        max_length=10, choices=BugPriority.choices, default=BugPriority.MEDIUM
    )
    severity = models.CharField(
        max_length=10, choices=BugSeverity.choices, default=BugSeverity.MAJOR
    )

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reported_bugs"
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_bugs",
    )

    due_date = models.DateField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    version = models.PositiveIntegerField(default=1)

    tags = models.ManyToManyField(Tag, blank=True, related_name="bugs")
    watchers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="watched_bugs"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "number"], name="unique_bug_number_per_project"
            ),
            models.UniqueConstraint(fields=["organization", "key"], name="unique_bug_key_per_org"),
        ]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "project", "status"]),
            models.Index(fields=["organization", "assignee"]),
            models.Index(fields=["organization", "reporter"]),
            models.Index(fields=["organization", "archived_at", "created_at"]),
            models.Index(fields=["organization", "priority"]),
            models.Index(fields=["organization", "severity"]),
            models.Index(fields=["organization", "due_date"]),
            models.Index(fields=["organization", "resolved_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.key} - {self.title}"


class BugRelationship(OrganizationScopedModel):
    """A directed link between two bugs.

    `relates_to` is semantically symmetric but stored as a single directed
    row — apps.bugs.services canonicalizes (from_bug, to_bug) by sorting on
    id before saving, so "A relates_to B" and "B relates_to A" can never
    both exist; the unique constraint below then guards the canonical pair.
    `blocks` and `duplicate_of` are genuinely directional and stored as-is;
    "blocked by" is derived for display from the inverse `blocks` row,
    never stored separately.
    """

    from_bug = models.ForeignKey(Bug, on_delete=models.CASCADE, related_name="relationships_from")
    to_bug = models.ForeignKey(Bug, on_delete=models.CASCADE, related_name="relationships_to")
    relationship_type = models.CharField(max_length=20, choices=RelationshipType.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_bug", "to_bug", "relationship_type"], name="unique_bug_relationship"
            ),
            models.CheckConstraint(
                condition=~Q(from_bug=F("to_bug")), name="bug_relationship_no_self_reference"
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "from_bug"]),
            models.Index(fields=["organization", "to_bug"]),
        ]

    def __str__(self) -> str:
        return f"{self.from_bug_id} {self.relationship_type} {self.to_bug_id}"
