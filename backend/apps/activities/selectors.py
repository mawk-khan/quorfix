from django.db.models import QuerySet

from apps.activities.models import BugActivity


def list_bug_activity(bug) -> QuerySet[BugActivity]:
    """Newest first, with a stable tie-breaker (-id) for rows created in the
    same instant under concurrent mutations, so pagination never reorders
    already-seen rows across pages."""
    return (
        BugActivity.objects.filter(organization=bug.organization, bug=bug)
        .select_related("actor")
        .order_by("-created_at", "-id")
    )
