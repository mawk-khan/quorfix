import uuid

import pytest

from apps.activities.models import ActivityVerb, BugActivity
from apps.comments.mentions import extract_mention_user_ids, resolve_mentions
from apps.comments.models import Mention
from apps.organizations.models import CommunityRole, Organization, OrganizationMembership


def mention_token(display_name: str, user_id) -> str:
    return f"@[{display_name}](mention:{user_id})"


@pytest.mark.django_db
class TestMentionExtractionAndStorageViaApi:
    def test_valid_same_org_mention_stored(
        self, admin_client, bug, developer_user, developer_membership
    ):
        body = f"Hey {mention_token('Dev', developer_user.pk)}, can you look at this?"
        response = admin_client.post(f"/api/bugs/{bug.pk}/comments/", {"body": body}, format="json")
        assert response.status_code == 201
        comment_id = response.json()["id"]

        assert Mention.objects.filter(comment_id=comment_id, mentioned_user=developer_user).exists()
        mentions_out = response.json()["mentions"]
        assert len(mentions_out) == 1
        assert mentions_out[0]["mentioned_user"]["id"] == str(developer_user.pk)

    def test_repeated_mention_token_creates_one_row(
        self, admin_client, bug, developer_user, developer_membership
    ):
        token = mention_token("Dev", developer_user.pk)
        body = f"{token} are you there? {token} please respond."
        response = admin_client.post(f"/api/bugs/{bug.pk}/comments/", {"body": body}, format="json")
        assert response.status_code == 201
        comment_id = response.json()["id"]

        assert (
            Mention.objects.filter(comment_id=comment_id, mentioned_user=developer_user).count()
            == 1
        )

    def test_foreign_org_uuid_ignored(self, admin_client, bug):
        other_org = Organization.objects.create(name="Other Co", slug="other-co-mentions")
        from django.contrib.auth import get_user_model

        foreign_user = get_user_model().objects.create_user(
            username="foreign-mentions", email="foreign-mentions@example.com", password="x"
        )
        OrganizationMembership.objects.create(
            organization=other_org, user=foreign_user, role=CommunityRole.DEVELOPER
        )
        body = mention_token("Foreign", foreign_user.pk)
        response = admin_client.post(f"/api/bugs/{bug.pk}/comments/", {"body": body}, format="json")
        assert response.status_code == 201

        assert not Mention.objects.filter(mentioned_user=foreign_user).exists()
        assert response.json()["mentions"] == []
        # The body is stored as submitted, invalid mention and all — we never
        # rewrite it server-side.
        assert response.json()["body"] == body

    def test_non_member_uuid_ignored(self, admin_client, bug):
        # A syntactically valid UUID that belongs to nobody at all.
        random_id = uuid.uuid4()
        body = mention_token("Nobody", random_id)
        response = admin_client.post(f"/api/bugs/{bug.pk}/comments/", {"body": body}, format="json")
        assert response.status_code == 201
        assert response.json()["mentions"] == []

    def test_invalid_token_ignored_safely(self, admin_client, bug):
        # Matches the token shape (36 chars of hex/hyphen) but is not a
        # well-formed UUID once hyphens are stripped.
        bad_id = "a" * 35 + "-"
        body = f"@[Someone](mention:{bad_id}) please look"
        response = admin_client.post(f"/api/bugs/{bug.pk}/comments/", {"body": body}, format="json")
        assert response.status_code == 201
        assert response.json()["mentions"] == []
        assert response.json()["body"] == body

    def test_display_name_not_trusted_for_identity(
        self, admin_client, bug, developer_user, developer_membership
    ):
        # The display name is an arbitrary string — resolution is entirely by
        # UUID, never by the name text.
        body = mention_token("Totally Someone Else", developer_user.pk)
        response = admin_client.post(f"/api/bugs/{bug.pk}/comments/", {"body": body}, format="json")
        assert response.status_code == 201
        assert response.json()["mentions"][0]["mentioned_user"]["id"] == str(developer_user.pk)

    def test_one_activity_per_valid_newly_created_mention(
        self, admin_client, bug, developer_user, developer_membership, qa_user, qa_membership
    ):
        body = f"{mention_token('Dev', developer_user.pk)} {mention_token('QA', qa_user.pk)}"
        response = admin_client.post(f"/api/bugs/{bug.pk}/comments/", {"body": body}, format="json")
        assert response.status_code == 201
        comment_id = response.json()["id"]

        activities = BugActivity.objects.filter(bug=bug, verb=ActivityVerb.MENTION_CREATED)
        assert activities.count() == 2
        mentioned_ids = {a.metadata["mentioned_user_id"] for a in activities}
        assert mentioned_ids == {str(developer_user.pk), str(qa_user.pk)}
        assert all(a.metadata["comment_id"] == comment_id for a in activities)

    def test_no_activity_for_invalid_mention(self, admin_client, bug):
        random_id = uuid.uuid4()
        body = mention_token("Nobody", random_id)
        admin_client.post(f"/api/bugs/{bug.pk}/comments/", {"body": body}, format="json")
        assert not BugActivity.objects.filter(bug=bug, verb=ActivityVerb.MENTION_CREATED).exists()

    def test_comment_added_activity_recorded_alongside_mentions(
        self, admin_client, bug, developer_user, developer_membership
    ):
        body = mention_token("Dev", developer_user.pk)
        admin_client.post(f"/api/bugs/{bug.pk}/comments/", {"body": body}, format="json")
        assert BugActivity.objects.filter(bug=bug, verb=ActivityVerb.COMMENT_ADDED).count() == 1


class TestExtractMentionUserIds:
    def test_dedupes_repeated_tokens_preserving_order(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        body = (
            f"{mention_token('A', a)} middle text {mention_token('B', b)} {mention_token('A', a)}"
        )
        assert extract_mention_user_ids(body) == [a, b]

    def test_ignores_malformed_uuid_segment(self):
        bad_id = "a" * 35 + "-"
        body = f"@[X](mention:{bad_id})"
        assert extract_mention_user_ids(body) == []

    def test_no_tokens_returns_empty_list(self):
        assert extract_mention_user_ids("just plain text, no mentions here") == []

    def test_does_not_match_ordinary_markdown_links(self):
        body = "See [the docs](https://example.com/mention:not-real) for details."
        assert extract_mention_user_ids(body) == []


@pytest.mark.django_db
class TestResolveMentions:
    def test_filters_to_organization_members_only(
        self, organization, developer_user, developer_membership
    ):
        other_org = Organization.objects.create(name="Other Co", slug="other-co-resolve")
        from django.contrib.auth import get_user_model

        foreign_user = get_user_model().objects.create_user(
            username="foreign-resolve", email="foreign-resolve@example.com", password="x"
        )
        OrganizationMembership.objects.create(
            organization=other_org, user=foreign_user, role=CommunityRole.DEVELOPER
        )
        candidate_ids = [developer_user.pk, foreign_user.pk, uuid.uuid4()]
        resolved = resolve_mentions(organization, candidate_ids)
        assert resolved == [developer_user.pk]

    def test_empty_input_returns_empty_list(self, organization):
        assert resolve_mentions(organization, []) == []
