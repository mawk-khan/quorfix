from django.db.models import QuerySet

from apps.comments.models import Comment


def get_comments_for_bug(bug) -> QuerySet[Comment]:
    """Bare organization+bug-scoped queryset for get_object_or_404 lookups —
    mirrors apps.bugs.selectors.get_bugs_for_organization."""
    return Comment.objects.filter(organization=bug.organization, bug=bug)


def get_comment_for_bug(bug) -> QuerySet[Comment]:
    """select_related/prefetch_related version for single-object and list
    lookups, so serializing a comment (including its mentions) never costs an
    extra query per row."""
    return (
        get_comments_for_bug(bug)
        .select_related("author")
        .prefetch_related("mentions__mentioned_user")
    )


def list_comments_for_bug(bug) -> QuerySet[Comment]:
    """Oldest-first with a stable id tie-breaker — a discussion reads top to
    bottom like a conversation, unlike the newest-first bug activity feed."""
    return get_comment_for_bug(bug).order_by("created_at", "id")
