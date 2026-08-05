import pytest

from apps.comments.models import Mention
from apps.notifications.resolvers import (
    mentioned_user_ids_for_comment,
    resolve_assignment_recipients,
    resolve_mention_recipients,
    resolve_watcher_recipients,
)


@pytest.mark.django_db
class TestResolveAssignmentRecipients:
    def test_returns_the_new_assignee(self, bug, developer_user, developer_membership, admin_user):
        recipients = resolve_assignment_recipients(bug, developer_user.pk, admin_user.pk)
        assert recipients == [developer_user]

    def test_excludes_self_assignment(self, bug, admin_user, admin_membership):
        assert resolve_assignment_recipients(bug, admin_user.pk, admin_user.pk) == []

    def test_none_assignee_yields_no_recipients(self, bug, admin_user):
        assert resolve_assignment_recipients(bug, None, admin_user.pk) == []

    def test_excludes_removed_member(self, bug, developer_user, developer_membership, admin_user):
        developer_membership.delete()
        assert resolve_assignment_recipients(bug, developer_user.pk, admin_user.pk) == []


@pytest.mark.django_db
class TestResolveMentionRecipients:
    def test_derives_from_persisted_mention_rows(
        self,
        bug,
        organization,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        make_comment,
    ):
        comment = make_comment(bug, admin_user, membership=admin_membership)
        Mention.objects.create(
            organization=organization, comment=comment, mentioned_user=developer_user
        )

        recipients = resolve_mention_recipients(comment, admin_user.pk)
        assert recipients == [developer_user]

    def test_excludes_actor_even_if_self_mentioned(
        self, bug, organization, admin_user, admin_membership, make_comment
    ):
        comment = make_comment(bug, admin_user, membership=admin_membership)
        Mention.objects.create(
            organization=organization, comment=comment, mentioned_user=admin_user
        )

        assert resolve_mention_recipients(comment, admin_user.pk) == []

    def test_revalidates_membership_at_call_time(
        self,
        bug,
        organization,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        make_comment,
    ):
        comment = make_comment(bug, admin_user, membership=admin_membership)
        Mention.objects.create(
            organization=organization, comment=comment, mentioned_user=developer_user
        )
        developer_membership.delete()

        assert resolve_mention_recipients(comment, admin_user.pk) == []

    def test_no_mentions_yields_empty_list(self, bug, admin_user, admin_membership, make_comment):
        comment = make_comment(bug, admin_user, membership=admin_membership)
        assert resolve_mention_recipients(comment, admin_user.pk) == []


@pytest.mark.django_db
class TestResolveWatcherRecipients:
    def test_returns_watchers_excluding_actor(
        self, bug, developer_user, developer_membership, admin_user
    ):
        bug.watchers.add(developer_user, admin_user)
        recipients = resolve_watcher_recipients(bug, admin_user.pk)
        assert recipients == [developer_user]

    def test_excludes_given_ids(
        self, bug, developer_user, developer_membership, qa_user, qa_membership, admin_user
    ):
        bug.watchers.add(developer_user, qa_user)
        recipients = resolve_watcher_recipients(
            bug, admin_user.pk, exclude_user_ids=frozenset({str(developer_user.pk)})
        )
        assert recipients == [qa_user]

    def test_viewer_watcher_is_eligible(self, bug, viewer_user, viewer_membership, admin_user):
        bug.watchers.add(viewer_user)
        assert resolve_watcher_recipients(bug, admin_user.pk) == [viewer_user]

    def test_excludes_removed_member(self, bug, developer_user, developer_membership, admin_user):
        bug.watchers.add(developer_user)
        developer_membership.delete()
        assert resolve_watcher_recipients(bug, admin_user.pk) == []

    def test_no_watchers_yields_empty_list(self, bug, admin_user):
        assert resolve_watcher_recipients(bug, admin_user.pk) == []


@pytest.mark.django_db
class TestMentionedUserIdsForComment:
    def test_returns_raw_ids_unfiltered_by_membership(
        self,
        bug,
        organization,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        make_comment,
    ):
        comment = make_comment(bug, admin_user, membership=admin_membership)
        Mention.objects.create(
            organization=organization, comment=comment, mentioned_user=developer_user
        )
        developer_membership.delete()  # removed, but the raw set still reports it

        assert mentioned_user_ids_for_comment(comment) == {str(developer_user.pk)}
