import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bugs.models import BugStatus
from apps.bugs.services import transition_bug

pytestmark = pytest.mark.django_db


def _trends(client, **params):
    response = client.get(reverse("analytics-trends"), params)
    assert response.status_code == 200, response.json()
    return response.json()


def _range(days=7):
    today = timezone.localdate()
    return {"date_from": str(today - datetime.timedelta(days=days)), "date_to": str(today)}


def _resolve_bug(bug, actor, membership):
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
        new_status=BugStatus.RESOLVED,
        expected_version=bug.version,
    )


class TestContinuousSeries:
    def test_series_covers_every_day_in_range_even_with_no_data(self, admin_client, project):
        data = _trends(admin_client, **_range(7))
        assert len(data) == 8  # inclusive of both endpoints
        assert all(point["created"] == 0 and point["resolved"] == 0 for point in data)

    def test_dates_are_in_ascending_order_with_no_gaps(self, admin_client, project):
        data = _trends(admin_client, **_range(7))
        dates = [datetime.date.fromisoformat(point["date"]) for point in data]
        assert dates == sorted(dates)
        assert dates[0] == dates[-1] - datetime.timedelta(days=7)
        for a, b in zip(dates, dates[1:], strict=False):
            assert (b - a).days == 1


class TestCreatedSeries:
    def test_bug_created_on_a_day_increments_that_day(
        self, admin_client, organization, project, admin_user, make_bug, backdate_bug, days_ago
    ):
        bug = make_bug(organization, project, admin_user)
        backdate_bug(bug, created_at=days_ago(3))
        data = _trends(admin_client, **_range(7))
        by_date = {point["date"]: point for point in data}
        target = str(timezone.localdate() - datetime.timedelta(days=3))
        assert by_date[target]["created"] == 1

    def test_bug_created_before_range_is_excluded(
        self, admin_client, organization, project, admin_user, make_bug, backdate_bug, days_ago
    ):
        bug = make_bug(organization, project, admin_user)
        backdate_bug(bug, created_at=days_ago(30))
        data = _trends(admin_client, **_range(7))
        assert sum(point["created"] for point in data) == 0

    def test_project_filter_narrows_created_series(
        self, admin_client, organization, project, make_project, admin_user, make_bug
    ):
        other = make_project(organization, key="OTH3", name="Other")
        make_bug(organization, project, admin_user)
        make_bug(organization, other, admin_user)
        data = _trends(admin_client, project=str(project.pk), **_range(7))
        assert sum(point["created"] for point in data) == 1


class TestResolvedSeries:
    def test_resolution_event_increments_the_day_it_happened(
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
            bug, verb="status_changed", to_value=BugStatus.RESOLVED, created_at=days_ago(2)
        )
        data = _trends(admin_client, **_range(7))
        by_date = {point["date"]: point for point in data}
        target = str(timezone.localdate() - datetime.timedelta(days=2))
        assert by_date[target]["resolved"] == 1

    def test_reopened_bug_still_shows_original_resolution_day(
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
            bug, verb="status_changed", to_value=BugStatus.RESOLVED, created_at=days_ago(2)
        )
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.REOPENED,
            expected_version=bug.version,
        )
        data = _trends(admin_client, **_range(7))
        by_date = {point["date"]: point for point in data}
        target = str(timezone.localdate() - datetime.timedelta(days=2))
        assert by_date[target]["resolved"] == 1
