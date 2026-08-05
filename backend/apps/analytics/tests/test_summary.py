import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bugs.models import BugStatus
from apps.bugs.services import archive_bug, transition_bug
from apps.projects.services import archive_project

pytestmark = pytest.mark.django_db


def _summary(client, **params):
    response = client.get(reverse("analytics-summary"), params)
    assert response.status_code == 200, response.json()
    return response.json()


def _range(days=7):
    today = timezone.localdate()
    return {"date_from": str(today - datetime.timedelta(days=days)), "date_to": str(today)}


def _resolve_bug(bug, actor, membership, new_status=BugStatus.RESOLVED):
    """Walks NEW -> TRIAGED -> IN_PROGRESS -> new_status — RESOLVED is only
    reachable from IN_PROGRESS/READY_FOR_QA in COMMUNITY_TRANSITIONS, and
    IN_PROGRESS requires an assignee."""
    bug = transition_bug(
        bug=bug,
        actor=actor,
        membership=membership,
        new_status=BugStatus.TRIAGED,
        expected_version=bug.version,
    )
    bug = transition_bug(
        bug=bug,
        actor=actor,
        membership=membership,
        new_status=BugStatus.IN_PROGRESS,
        expected_version=bug.version,
        assignee_id=str(actor.pk),
    )
    return transition_bug(
        bug=bug,
        actor=actor,
        membership=membership,
        new_status=new_status,
        expected_version=bug.version,
    )


class TestOpenCount:
    def test_new_bug_counts_as_open(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user)
        data = _summary(admin_client, **_range())
        assert data["open_bugs"] == 1

    def test_resolved_bug_does_not_count_as_open(
        self, admin_client, organization, project, admin_user, admin_membership, make_bug
    ):
        bug = make_bug(organization, project, admin_user)
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.CANNOT_REPRODUCE,
            expected_version=bug.version,
        )
        data = _summary(admin_client, **_range())
        assert data["open_bugs"] == 0

    def test_reopened_bug_counts_as_open(
        self, admin_client, organization, project, admin_user, admin_membership, make_bug
    ):
        bug = make_bug(organization, project, admin_user)
        bug = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.WONT_FIX,
            expected_version=bug.version,
        )
        bug = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.REOPENED,
            expected_version=bug.version,
        )
        data = _summary(admin_client, **_range())
        assert data["open_bugs"] == 1

    def test_archived_bug_excluded(
        self, admin_client, organization, project, admin_user, admin_membership, make_bug
    ):
        bug = make_bug(organization, project, admin_user)
        archive_bug(
            bug=bug, actor=admin_user, membership=admin_membership, expected_version=bug.version
        )
        data = _summary(admin_client, **_range())
        assert data["open_bugs"] == 0

    def test_bug_in_archived_project_excluded(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user)
        archive_project(project=project)
        data = _summary(admin_client, **_range())
        assert data["open_bugs"] == 0

    def test_project_filter_narrows_open_count(
        self, admin_client, organization, project, make_project, admin_user, make_bug
    ):
        other = make_project(organization, key="OTH2", name="Other")
        make_bug(organization, project, admin_user)
        make_bug(organization, other, admin_user)
        data = _summary(admin_client, project=str(project.pk), **_range())
        assert data["open_bugs"] == 1

    def test_open_count_ignores_date_range(
        self, admin_client, organization, project, admin_user, make_bug, backdate_bug, days_ago
    ):
        bug = make_bug(organization, project, admin_user)
        backdate_bug(bug, created_at=days_ago(200))
        today = timezone.localdate()
        data = _summary(
            admin_client,
            date_from=str(today - datetime.timedelta(days=1)),
            date_to=str(today),
        )
        assert data["open_bugs"] == 1


class TestOverdueCount:
    def test_open_bug_past_due_date_is_overdue(
        self, admin_client, organization, project, admin_user, make_bug, backdate_bug
    ):
        bug = make_bug(organization, project, admin_user)
        backdate_bug(bug, due_date=timezone.localdate() - datetime.timedelta(days=1))
        data = _summary(admin_client, **_range())
        assert data["overdue_bugs"] == 1

    def test_bug_without_due_date_is_not_overdue(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user)
        data = _summary(admin_client, **_range())
        assert data["overdue_bugs"] == 0

    def test_resolved_bug_past_due_date_is_not_overdue(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        backdate_bug,
    ):
        bug = make_bug(organization, project, admin_user)
        backdate_bug(bug, due_date=timezone.localdate() - datetime.timedelta(days=1))
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.WONT_FIX,
            expected_version=bug.version,
        )
        data = _summary(admin_client, **_range())
        assert data["overdue_bugs"] == 0

    def test_due_today_is_not_overdue(
        self, admin_client, organization, project, admin_user, make_bug, backdate_bug
    ):
        bug = make_bug(organization, project, admin_user)
        backdate_bug(bug, due_date=timezone.localdate())
        data = _summary(admin_client, **_range())
        assert data["overdue_bugs"] == 0

    def test_overdue_ignores_date_range(
        self, admin_client, organization, project, admin_user, make_bug, backdate_bug
    ):
        bug = make_bug(organization, project, admin_user)
        backdate_bug(bug, due_date=timezone.localdate() - datetime.timedelta(days=100))
        today = timezone.localdate()
        data = _summary(
            admin_client,
            date_from=str(today - datetime.timedelta(days=1)),
            date_to=str(today),
        )
        assert data["overdue_bugs"] == 1

    def test_archived_project_excludes_overdue(
        self, admin_client, organization, project, admin_user, make_bug, backdate_bug
    ):
        bug = make_bug(organization, project, admin_user)
        backdate_bug(bug, due_date=timezone.localdate() - datetime.timedelta(days=1))
        archive_project(project=project)
        data = _summary(admin_client, **_range())
        assert data["overdue_bugs"] == 0


class TestNewBugsInRange:
    def test_created_at_inside_range_counts(
        self, admin_client, organization, project, admin_user, make_bug, backdate_bug, days_ago
    ):
        bug = make_bug(organization, project, admin_user)
        backdate_bug(bug, created_at=days_ago(3))
        data = _summary(admin_client, **_range(7))
        assert data["new_bugs"] == 1

    def test_created_at_outside_range_excluded(
        self, admin_client, organization, project, admin_user, make_bug, backdate_bug, days_ago
    ):
        bug = make_bug(organization, project, admin_user)
        backdate_bug(bug, created_at=days_ago(30))
        data = _summary(admin_client, **_range(7))
        assert data["new_bugs"] == 0

    def test_archived_bug_excluded_from_new_count(
        self, admin_client, organization, project, admin_user, admin_membership, make_bug
    ):
        bug = make_bug(organization, project, admin_user)
        archive_bug(
            bug=bug, actor=admin_user, membership=admin_membership, expected_version=bug.version
        )
        data = _summary(admin_client, **_range())
        assert data["new_bugs"] == 0


class TestResolvedBugsInRange:
    def test_resolution_transition_inside_range_counts(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        backdate_activity,
        days_ago,
    ):
        bug = make_bug(organization, project, admin_user)
        bug = _resolve_bug(bug, admin_user, admin_membership)
        backdate_activity(
            bug, verb="status_changed", to_value=BugStatus.RESOLVED, created_at=days_ago(3)
        )
        data = _summary(admin_client, **_range(7))
        assert data["resolved_bugs"] == 1

    def test_reopen_then_resolve_again_counts_twice(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        backdate_activity,
        days_ago,
    ):
        """Throughput semantics: two distinct resolution events in range
        both count, even though only one is reflected in the bug's current
        state."""
        bug = make_bug(organization, project, admin_user)
        bug = _resolve_bug(bug, admin_user, admin_membership)
        bug = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.REOPENED,
            expected_version=bug.version,
        )
        bug = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.IN_PROGRESS,
            expected_version=bug.version,
        )
        bug = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.RESOLVED,
            expected_version=bug.version,
        )
        from apps.activities.models import BugActivity

        resolved_events = BugActivity.objects.filter(
            bug=bug, verb="status_changed", to_value=BugStatus.RESOLVED
        ).order_by("created_at")
        assert resolved_events.count() == 2
        resolved_events.update(created_at=days_ago(3))

        data = _summary(admin_client, **_range(7))
        assert data["resolved_bugs"] == 2

    def test_closed_is_not_a_second_resolution_event(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        backdate_activity,
        days_ago,
    ):
        bug = make_bug(organization, project, admin_user)
        bug = _resolve_bug(bug, admin_user, admin_membership)
        bug = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.CLOSED,
            expected_version=bug.version,
        )
        backdate_activity(
            bug, verb="status_changed", to_value=BugStatus.RESOLVED, created_at=days_ago(3)
        )
        backdate_activity(
            bug, verb="status_changed", to_value=BugStatus.CLOSED, created_at=days_ago(2)
        )
        data = _summary(admin_client, **_range(7))
        assert data["resolved_bugs"] == 1

    def test_resolution_event_outside_range_excluded(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        backdate_activity,
        days_ago,
    ):
        bug = make_bug(organization, project, admin_user)
        bug = _resolve_bug(bug, admin_user, admin_membership)
        backdate_activity(
            bug, verb="status_changed", to_value=BugStatus.RESOLVED, created_at=days_ago(30)
        )
        data = _summary(admin_client, **_range(7))
        assert data["resolved_bugs"] == 0


class TestEmptyDataset:
    def test_all_zero_for_fresh_project(self, admin_client, project):
        data = _summary(admin_client, **_range())
        assert data == {
            "open_bugs": 0,
            "overdue_bugs": 0,
            "new_bugs": 0,
            "resolved_bugs": 0,
        }
