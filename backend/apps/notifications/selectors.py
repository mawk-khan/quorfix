from django.db.models import QuerySet

from apps.notifications.models import Notification


def get_notifications_for_recipient(organization, recipient) -> QuerySet[Notification]:
    """Bare organization+recipient-scoped queryset — recipient is always
    request.user, never client-supplied, so this is also the ownership
    check: a notification outside this queryset is indistinguishable from
    one that doesn't exist (get_object_or_404 on it 404s, not 403)."""
    return Notification.objects.filter(organization=organization, recipient=recipient)


def get_notification_for_recipient(organization, recipient) -> QuerySet[Notification]:
    """select_related version for list/detail-shaped reads — mirrors
    apps.bugs.selectors.get_bug_for_organization's identical split between
    the bare and select_related querysets."""
    return get_notifications_for_recipient(organization, recipient).select_related(
        "actor", "bug", "comment"
    )


def list_notifications(
    organization, recipient, *, read: bool | None = None, event_type: str | None = None
) -> QuerySet[Notification]:
    """Filtered, paginated-by-the-caller queryset for the list endpoint.
    Meta.ordering (-created_at, -id) already gives newest-first with a
    stable tie-breaker, so no explicit .order_by() is needed here."""
    qs = get_notification_for_recipient(organization, recipient)
    if read is True:
        qs = qs.filter(read_at__isnull=False)
    elif read is False:
        qs = qs.filter(read_at__isnull=True)
    if event_type:
        qs = qs.filter(event_type=event_type)
    return qs


def unread_count(organization, recipient) -> int:
    """A single bounded COUNT query — never loads the underlying rows."""
    return (
        get_notifications_for_recipient(organization, recipient)
        .filter(read_at__isnull=True)
        .count()
    )
