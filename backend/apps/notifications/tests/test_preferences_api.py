import pytest

from apps.notifications.models import NotificationEventType, NotificationPreference


@pytest.mark.django_db
class TestPreferenceList:
    def test_returns_all_five_community_event_types_even_with_no_rows(self, admin_client):
        response = admin_client.get("/api/notifications/preferences/")
        assert response.status_code == 200
        body = response.json()
        assert {row["event_type"] for row in body} == set(NotificationEventType.values)
        assert all(row["email_enabled"] is True for row in body)  # missing row -> enabled

    def test_reflects_an_existing_override(self, admin_client, organization, admin_user):
        NotificationPreference.objects.create(
            organization=organization,
            user=admin_user,
            event_type=NotificationEventType.MENTIONED,
            email_enabled=False,
        )
        response = admin_client.get("/api/notifications/preferences/")
        by_type = {row["event_type"]: row["email_enabled"] for row in response.json()}
        assert by_type[NotificationEventType.MENTIONED] is False
        assert by_type[NotificationEventType.COMMENT_ADDED] is True

    def test_does_not_issue_one_query_per_event_type(
        self, admin_client, django_assert_max_num_queries
    ):
        with django_assert_max_num_queries(4):
            admin_client.get("/api/notifications/preferences/")

    def test_only_the_callers_own_preferences_are_returned(
        self, admin_client, organization, admin_user, developer_user, developer_membership
    ):
        NotificationPreference.objects.create(
            organization=organization,
            user=developer_user,
            event_type=NotificationEventType.MENTIONED,
            email_enabled=False,
        )
        response = admin_client.get("/api/notifications/preferences/")
        by_type = {row["event_type"]: row["email_enabled"] for row in response.json()}
        assert (
            by_type[NotificationEventType.MENTIONED] is True
        )  # admin's own row is still missing -> enabled


@pytest.mark.django_db
class TestPreferenceUpdate:
    def test_upserts_when_no_row_exists(self, admin_client, organization, admin_user):
        response = admin_client.patch(
            "/api/notifications/preferences/mentioned/", {"email_enabled": False}, format="json"
        )
        assert response.status_code == 200
        assert response.json() == {"event_type": "mentioned", "email_enabled": False}
        assert (
            NotificationPreference.objects.get(
                organization=organization,
                user=admin_user,
                event_type=NotificationEventType.MENTIONED,
            ).email_enabled
            is False
        )

    def test_updates_an_existing_row(self, admin_client, organization, admin_user):
        NotificationPreference.objects.create(
            organization=organization,
            user=admin_user,
            event_type=NotificationEventType.MENTIONED,
            email_enabled=False,
        )
        response = admin_client.patch(
            "/api/notifications/preferences/mentioned/", {"email_enabled": True}, format="json"
        )
        assert response.status_code == 200
        assert (
            NotificationPreference.objects.filter(
                organization=organization,
                user=admin_user,
                event_type=NotificationEventType.MENTIONED,
            ).count()
            == 1
        )

    def test_unknown_event_type_returns_400(self, admin_client):
        response = admin_client.patch(
            "/api/notifications/preferences/not_a_real_type/",
            {"email_enabled": False},
            format="json",
        )
        assert response.status_code == 400

    def test_missing_email_enabled_returns_400(self, admin_client):
        response = admin_client.patch(
            "/api/notifications/preferences/mentioned/", {}, format="json"
        )
        assert response.status_code == 400

    def test_organization_and_user_id_in_body_are_ignored(
        self, admin_client, organization, admin_user, developer_user, developer_membership
    ):
        """A client can never redirect the update to another user or
        organization by stuffing extra fields into the body — the
        serializer only ever reads email_enabled; organization/user always
        come from request.organization/request.user."""
        response = admin_client.patch(
            "/api/notifications/preferences/mentioned/",
            {
                "email_enabled": False,
                "user": str(developer_user.pk),
                "organization": "not-a-real-org-id",
            },
            format="json",
        )
        assert response.status_code == 200
        assert (
            NotificationPreference.objects.get(
                organization=organization,
                user=admin_user,
                event_type=NotificationEventType.MENTIONED,
            ).email_enabled
            is False
        )
        assert not NotificationPreference.objects.filter(user=developer_user).exists()

    def test_preference_change_does_not_bump_bug_version_or_create_activity(
        self, admin_client, bug, organization, admin_user
    ):
        from apps.activities.models import BugActivity

        version_before = bug.version
        activity_count_before = BugActivity.objects.filter(bug=bug).count()
        admin_client.patch(
            "/api/notifications/preferences/mentioned/", {"email_enabled": False}, format="json"
        )
        bug.refresh_from_db()
        assert bug.version == version_before
        assert BugActivity.objects.filter(bug=bug).count() == activity_count_before

    def test_cross_organization_user_cannot_be_addressed(
        self, admin_client, organization, admin_user
    ):
        """There is no per-user URL identifier for preferences — every
        request is implicitly scoped to request.user/request.organization —
        so there is no cross-organization object to enumerate in the first
        place; this documents that invariant rather than probing a 404 that
        can't structurally occur here."""
        from django.contrib.auth import get_user_model

        from apps.organizations.models import CommunityRole, Organization, OrganizationMembership

        other_org = Organization.objects.create(name="Other Co", slug="other-co-notif-prefs")
        other_admin = get_user_model().objects.create_user(
            username="other-org-admin-notif-prefs",
            email="other-org-admin-notif-prefs@example.com",
            password="x",
        )
        OrganizationMembership.objects.create(
            organization=other_org, user=other_admin, role=CommunityRole.ADMINISTRATOR
        )
        NotificationPreference.objects.create(
            organization=other_org,
            user=other_admin,
            event_type=NotificationEventType.MENTIONED,
            email_enabled=False,
        )

        response = admin_client.get("/api/notifications/preferences/")
        by_type = {row["event_type"]: row["email_enabled"] for row in response.json()}
        assert by_type[NotificationEventType.MENTIONED] is True  # unaffected by the other org's row
