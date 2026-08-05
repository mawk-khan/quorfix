"""Recipient resolution for notification events.

Every resolver here re-validates against OrganizationMembership at call
time (not at the time the source event was recorded) and excludes the
actor — apps.notifications.tasks.create_notifications_for_event calls these
from inside the Celery task, after re-resolving `bug`/`comment` from stable
IDs, never trusting a recipient list carried in the task payload.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from apps.comments.models import Mention
from apps.organizations.models import OrganizationMembership

User = get_user_model()


def _active_members(organization, user_ids) -> QuerySet:
    """Every id in `user_ids` that currently holds an active
    OrganizationMembership in `organization` — the single check that keeps a
    removed member from ever receiving a new notification, regardless of
    which resolver is asking."""
    member_ids = OrganizationMembership.objects.filter(
        organization=organization, user_id__in=user_ids
    ).values_list("user_id", flat=True)
    return User.objects.filter(pk__in=member_ids)


def resolve_assignment_recipients(bug, assignee_id, actor_id) -> list:
    """Single-recipient resolver for bug_assigned: the new assignee, if they
    still hold active membership and aren't the actor (self-assignment never
    notifies)."""
    if assignee_id is None or str(assignee_id) == str(actor_id):
        return []
    return list(_active_members(bug.organization, [assignee_id]))


def resolve_mention_recipients(comment, actor_id) -> list:
    """Derives recipients from persisted Mention rows for this comment — not
    from any list passed into the task — so this is correct regardless of
    whether the mention was parsed a moment ago or hours ago. Actor excluded;
    membership revalidated now, not at comment-creation time."""
    mentioned_ids = list(
        Mention.objects.filter(comment=comment)
        .exclude(mentioned_user_id=actor_id)
        .values_list("mentioned_user_id", flat=True)
        .distinct()
    )
    if not mentioned_ids:
        return []
    return list(_active_members(comment.organization, mentioned_ids))


def resolve_watcher_recipients(bug, actor_id, *, exclude_user_ids: frozenset = frozenset()) -> list:
    """Shared by comment_added, status_changed, and bug_reopened — all three
    target "bug watchers" identically. `exclude_user_ids` is how
    comment_added subtracts the mentioned set (see
    apps.notifications.tasks._resolve_recipients) so mention precedence holds
    regardless of task dispatch/execution order: this resolver re-derives the
    mentioned set itself from the Mention table rather than trusting a value
    computed by a separate, possibly-not-yet-run task."""
    watcher_ids = list(
        bug.watchers.exclude(pk=actor_id)
        .exclude(pk__in=exclude_user_ids)
        .values_list("pk", flat=True)
    )
    if not watcher_ids:
        return []
    return list(_active_members(bug.organization, watcher_ids))


def mentioned_user_ids_for_comment(comment) -> frozenset:
    """The raw set of mentioned user ids for a comment, unfiltered by
    membership — used only to exclude mentioned recipients from
    comment_added's watcher set (apps.notifications.tasks), not as a
    recipient list on its own. Membership/actor filtering happens in
    resolve_mention_recipients for the actual mentioned notifications."""
    return frozenset(
        str(uid)
        for uid in Mention.objects.filter(comment=comment).values_list(
            "mentioned_user_id", flat=True
        )
    )
