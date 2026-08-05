import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bugs.models import BugStatus
from apps.bugs.services import assign_bug, transition_bug
from apps.organizations.services import change_member_role, remove_member

pytestmark = pytest.mark.django_db


def _workload(client, **params):
    response = client.get(reverse("analytics-workload"), params)
    assert response.status_code == 200, response.json()
    return response.json()


def _assign(bug, assignee, actor, membership):
    return assign_bug(
        bug=bug,
        actor=actor,
        membership=membership,
        assignee_id=str(assignee.pk),
        expected_version=bug.version,
    )


class TestEligibleWorkload:
    def test_bug_assigned_to_staff_member_is_eligible(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        make_bug,
    ):
        bug = make_bug(organization, project, admin_user)
        _assign(bug, developer_user, admin_user, admin_membership)
        data = _workload(admin_client)
        assert data["eligible"] == [
            {
                "user_id": str(developer_user.pk),
                "name": f"{developer_user.first_name} {developer_user.last_name}".strip()
                or developer_user.email,
                "role": "developer",
                "count": 1,
            }
        ]
        assert data["needs_reassignment"] == []

    def test_only_open_statuses_counted(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        make_bug,
    ):
        bug = make_bug(organization, project, admin_user)
        bug = _assign(bug, developer_user, admin_user, admin_membership)
        bug = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.TRIAGED,
            expected_version=bug.version,
        )
        bug = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.IN_PROGRESS,
            expected_version=bug.version,
        )
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.RESOLVED,
            expected_version=bug.version,
        )
        data = _workload(admin_client)
        assert data["eligible"] == []

    def test_multiple_eligible_assignees_sorted_by_count_desc(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        qa_user,
        qa_membership,
        make_bug,
    ):
        b1 = make_bug(organization, project, admin_user, title="Bug 1")
        b2 = make_bug(organization, project, admin_user, title="Bug 2")
        b3 = make_bug(organization, project, admin_user, title="Bug 3")
        _assign(b1, developer_user, admin_user, admin_membership)
        _assign(b2, developer_user, admin_user, admin_membership)
        _assign(b3, qa_user, admin_user, admin_membership)
        data = _workload(admin_client)
        counts = [(row["user_id"], row["count"]) for row in data["eligible"]]
        assert counts[0] == (str(developer_user.pk), 2)
        assert counts[1] == (str(qa_user.pk), 1)

    def test_ignores_date_range_query_params(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        make_bug,
    ):
        bug = make_bug(organization, project, admin_user)
        _assign(bug, developer_user, admin_user, admin_membership)
        today = timezone.localdate()
        data = _workload(
            admin_client,
            date_from=str(today - datetime.timedelta(days=1)),
            date_to=str(today),
        )
        assert data["eligible"][0]["count"] == 1


class TestUnassignedBucket:
    def test_bug_without_assignee_is_unassigned(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user)
        data = _workload(admin_client)
        assert data["unassigned"] == 1

    def test_removed_member_bugs_become_unassigned(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        make_bug,
    ):
        bug = make_bug(organization, project, admin_user)
        _assign(bug, developer_user, admin_user, admin_membership)
        remove_member(membership=developer_membership)
        data = _workload(admin_client)
        assert data["unassigned"] == 1
        assert data["eligible"] == []
        assert data["needs_reassignment"] == []


class TestNeedsReassignmentBucket:
    def test_assignee_demoted_to_reporter_appears_under_needs_reassignment(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        make_bug,
    ):
        bug = make_bug(organization, project, admin_user)
        _assign(bug, developer_user, admin_user, admin_membership)
        change_member_role(membership=developer_membership, new_role="reporter")
        data = _workload(admin_client)
        assert data["eligible"] == []
        assert data["unassigned"] == 0
        assert len(data["needs_reassignment"]) == 1
        entry = data["needs_reassignment"][0]
        assert entry["user_id"] == str(developer_user.pk)
        assert entry["role"] == "reporter"
        assert entry["count"] == 1

    def test_assignee_demoted_to_viewer_appears_under_needs_reassignment(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        qa_user,
        qa_membership,
        make_bug,
    ):
        bug = make_bug(organization, project, admin_user)
        _assign(bug, qa_user, admin_user, admin_membership)
        change_member_role(membership=qa_membership, new_role="viewer")
        data = _workload(admin_client)
        assert len(data["needs_reassignment"]) == 1
        assert data["needs_reassignment"][0]["role"] == "viewer"


class TestWorkloadTenantIsolation:
    def test_other_organization_workload_is_invisible(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        make_bug,
        other_organization,
        other_admin_user,
        other_admin_membership,
        other_project,
    ):
        bug = make_bug(organization, project, admin_user)
        _assign(bug, developer_user, admin_user, admin_membership)

        other_bug = make_bug(other_organization, other_project, other_admin_user)
        assign_bug(
            bug=other_bug,
            actor=other_admin_user,
            membership=other_admin_membership,
            assignee_id=str(other_admin_user.pk),
            expected_version=other_bug.version,
        )

        data = _workload(admin_client)
        eligible_ids = {row["user_id"] for row in data["eligible"]}
        assert str(other_admin_user.pk) not in eligible_ids
