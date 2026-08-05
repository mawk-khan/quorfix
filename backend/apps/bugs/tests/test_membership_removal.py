import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.activities.models import ActivityVerb, BugActivity
from apps.organizations.services import remove_member


@pytest.mark.django_db
class TestMembershipRemovalClearsAssignments:
    def test_clears_assignment_and_writes_system_activity(
        self,
        organization,
        project,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        bug,
    ):
        from apps.bugs.services import assign_bug

        assigned = assign_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            assignee_id=str(developer_user.pk),
            expected_version=bug.version,
        )
        assert assigned.assignee_id == developer_user.pk

        remove_member(membership=developer_membership)

        assigned.refresh_from_db()
        assert assigned.assignee is None
        assert assigned.version == 3  # created(1) -> assigned(2) -> unassigned(3)

        activity = BugActivity.objects.filter(bug=assigned, verb=ActivityVerb.UNASSIGNED).latest(
            "created_at"
        )
        assert (
            activity.actor is None
        )  # system-generated, not attributed to the admin who removed the member
        assert activity.metadata.get("reason") == "membership_removed"

    def test_only_affects_the_same_organization(
        self,
        organization,
        project,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        bug,
    ):
        from apps.bugs.services import assign_bug, clear_bug_assignments, create_bug
        from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
        from apps.projects.models import Project, ProjectStatus

        assign_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            assignee_id=str(developer_user.pk),
            expected_version=bug.version,
        )

        other_org = Organization.objects.create(name="Other Co", slug="other-co-membership")
        other_membership = OrganizationMembership.objects.create(
            organization=other_org, user=developer_user, role=CommunityRole.DEVELOPER
        )
        other_project = Project.objects.create(
            organization=other_org, key="OTH", name="Other", status=ProjectStatus.ACTIVE
        )
        other_bug = create_bug(
            organization=other_org,
            project=other_project,
            reporter=admin_user,
            membership=other_membership,
            title="Other org bug",
        )
        assign_bug(
            bug=other_bug,
            actor=admin_user,
            membership=other_membership,
            assignee_id=str(developer_user.pk),
            expected_version=other_bug.version,
        )

        cleared = clear_bug_assignments(organization=organization, user=developer_user)

        assert cleared == 1
        other_bug.refresh_from_db()
        assert other_bug.assignee_id == developer_user.pk  # untouched

    def test_no_op_when_nothing_assigned(self, organization, developer_user):
        from apps.bugs.services import clear_bug_assignments

        assert clear_bug_assignments(organization=organization, user=developer_user) == 0

    def test_bulk_safe_query_count_does_not_grow_with_assignment_count(
        self,
        organization,
        project,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        make_bug,
    ):
        """One UPDATE + one SELECT (for the activity bulk_create) regardless
        of how many bugs the removed member was assigned to — not one
        query per bug in a Python loop."""
        from apps.bugs.services import assign_bug, clear_bug_assignments

        bugs = [
            make_bug(
                organization, project, admin_user, membership=admin_membership, title=f"Bug {i}"
            )
            for i in range(30)
        ]
        for b in bugs:
            assign_bug(
                bug=b,
                actor=admin_user,
                membership=admin_membership,
                assignee_id=str(developer_user.pk),
                expected_version=b.version,
            )

        with CaptureQueriesContext(connection) as ctx:
            cleared = clear_bug_assignments(organization=organization, user=developer_user)

        assert cleared == 30
        # UPDATE + SELECT (with join) + bulk INSERT = a small constant, not 30+.
        assert len(ctx.captured_queries) <= 5
