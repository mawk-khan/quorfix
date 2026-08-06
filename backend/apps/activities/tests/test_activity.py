import pytest

from apps.activities.models import ActivityVerb, BugActivity
from apps.bugs.models import Bug
from apps.bugs.services import add_tag, transition_bug, update_bug
from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
from apps.projects.models import Project, ProjectStatus


@pytest.mark.django_db
class TestActivityRecording:
    def test_bug_creation_writes_activity(self, bug):
        assert BugActivity.objects.filter(bug=bug, verb=ActivityVerb.CREATED).exists()

    def test_each_mutation_type_writes_activity(self, bug, admin_user, admin_membership):
        update_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            expected_version=bug.version,
            title="New",
        )
        bug.refresh_from_db()
        assert BugActivity.objects.filter(bug=bug, verb=ActivityVerb.FIELD_UPDATED).exists()

        transitioned = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status="triaged",
            expected_version=bug.version,
        )
        assert BugActivity.objects.filter(bug=bug, verb=ActivityVerb.STATUS_CHANGED).exists()

        add_tag(
            bug=transitioned,
            actor=admin_user,
            membership=admin_membership,
            name="x",
            expected_version=transitioned.version,
        )
        assert BugActivity.objects.filter(bug=bug, verb=ActivityVerb.TAG_ADDED).exists()

    def test_activity_endpoint_only_supports_get(self, admin_client, bug):
        # The @action is registered methods=["get"] only — no update or
        # delete route exists for activity at any URL.
        response = admin_client.patch(f"/api/bugs/{bug.pk}/activity/", {}, format="json")
        assert response.status_code == 405
        response = admin_client.delete(f"/api/bugs/{bug.pk}/activity/")
        assert response.status_code == 405


@pytest.mark.django_db
class TestActivityFeedEndpoint:
    def test_paginated_newest_first(self, admin_client, bug, admin_user, admin_membership):
        for i in range(3):
            update_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                expected_version=bug.version,
                title=f"Title {i}",
            )
            bug.refresh_from_db()

        response = admin_client.get(f"/api/bugs/{bug.pk}/activity/")
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"count", "next", "previous", "results"}
        timestamps = [r["created_at"] for r in body["results"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_does_not_return_entire_history_unbounded(
        self, admin_client, bug, admin_user, admin_membership
    ):
        for i in range(40):
            update_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                expected_version=bug.version,
                title=f"Title {i}",
            )
            bug.refresh_from_db()

        response = admin_client.get(f"/api/bugs/{bug.pk}/activity/")
        body = response.json()
        assert body["count"] > 25  # more rows exist than were returned
        assert len(body["results"]) <= 25  # bounded by BoundedPageNumberPagination

    def test_viewer_can_read_activity(self, viewer_client, bug):
        response = viewer_client.get(f"/api/bugs/{bug.pk}/activity/")
        assert response.status_code == 200

    def test_metadata_contains_no_sensitive_fields(self, bug, admin_user, admin_membership):
        # A blunt structural guarantee: nothing this module ever writes
        # includes these keys, regardless of which verb produced the row.
        forbidden = {"password", "token", "cookie", "sessionid", "csrftoken", "secret"}
        update_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            expected_version=bug.version,
            title="x",
        )
        for activity in BugActivity.objects.filter(bug=bug):
            assert not (forbidden & set(k.lower() for k in activity.metadata.keys()))
            assert not any(f in activity.from_value.lower() for f in forbidden)
            assert not any(f in activity.to_value.lower() for f in forbidden)


@pytest.mark.django_db
class TestActivityFeedTenantIsolation:
    """The activity feed endpoint (GET /api/bugs/{pk}/activity/) is nested
    under a bug, not queried by its own ID — same-shaped gap as
    apps.bugs.tests.test_bug_tenant_isolation, checked directly here since
    that file only exercises the bug detail/mutation endpoints, never this
    nested one."""

    @pytest.fixture
    def other_org_bug(self):
        org = Organization.objects.create(name="Other Co", slug="other-co-activity-isolation")
        project = Project.objects.create(
            organization=org, key="OTH", name="Other", status=ProjectStatus.ACTIVE
        )
        from django.contrib.auth import get_user_model

        other_user = get_user_model().objects.create_user(
            username="other-org-admin-activity",
            email="other-org-admin-activity@example.com",
            password="x",
        )
        OrganizationMembership.objects.create(
            organization=org, user=other_user, role=CommunityRole.ADMINISTRATOR
        )
        return Bug.objects.create(
            organization=org,
            project=project,
            number=1,
            key="OTH-1",
            title="Other org's bug",
            reporter=other_user,
        )

    def test_cannot_read_another_organizations_bug_activity(self, admin_client, other_org_bug):
        response = admin_client.get(f"/api/bugs/{other_org_bug.pk}/activity/")
        assert response.status_code == 404
