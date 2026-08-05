import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bugs.models import BugStatus
from apps.bugs.services import transition_bug

pytestmark = pytest.mark.django_db


def _resolution_time(client, **params):
    response = client.get(reverse("analytics-resolution-time"), params)
    assert response.status_code == 200, response.json()
    return {row["priority"]: row["average_seconds"] for row in response.json()}


def _range(days=7):
    today = timezone.localdate()
    return {"date_from": str(today - datetime.timedelta(days=days)), "date_to": str(today)}


def _walk_to(bug, actor, membership, target_status, *, duplicate_of=None):
    """NEW -> TRIAGED -> target_status. RESOLVED additionally requires a
    detour through IN_PROGRESS (with an assignee); DUPLICATE additionally
    requires a target bug — both reachable directly from TRIAGED for the
    other RESOLUTION_STATUSES."""
    bug = transition_bug(
        bug=bug,
        actor=actor,
        membership=membership,
        new_status=BugStatus.TRIAGED,
        expected_version=bug.version,
    )
    if target_status == BugStatus.RESOLVED:
        bug = transition_bug(
            bug=bug,
            actor=actor,
            membership=membership,
            new_status=BugStatus.IN_PROGRESS,
            expected_version=bug.version,
            assignee_id=str(actor.pk),
        )
    kwargs = {"duplicate_of": duplicate_of} if target_status == BugStatus.DUPLICATE else {}
    return transition_bug(
        bug=bug,
        actor=actor,
        membership=membership,
        new_status=target_status,
        expected_version=bug.version,
        **kwargs,
    )


class TestPopulationByOutcome:
    @pytest.mark.parametrize(
        "target_status",
        [BugStatus.RESOLVED, BugStatus.DUPLICATE, BugStatus.CANNOT_REPRODUCE, BugStatus.WONT_FIX],
    )
    def test_resolution_status_is_included(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        backdate_bug,
        days_ago,
        target_status,
    ):
        duplicate_target = None
        if target_status == BugStatus.DUPLICATE:
            duplicate_target = str(
                make_bug(organization, project, admin_user, title="Target bug").pk
            )

        bug = make_bug(organization, project, admin_user, priority="high")
        backdate_bug(bug, created_at=days_ago(5))
        bug = _walk_to(
            bug, admin_user, admin_membership, target_status, duplicate_of=duplicate_target
        )
        backdate_bug(bug, resolved_at=days_ago(1))
        data = _resolution_time(admin_client, **_range(7))
        assert data["high"] is not None

    def test_average_duration_is_computed_correctly(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        backdate_bug,
        days_ago,
    ):
        bug = make_bug(organization, project, admin_user, priority="urgent")
        backdate_bug(bug, created_at=days_ago(5))
        bug = _walk_to(bug, admin_user, admin_membership, BugStatus.RESOLVED)
        backdate_bug(bug, resolved_at=days_ago(2))
        data = _resolution_time(admin_client, **_range(7))
        # 5 days ago -> 2 days ago is a 3-day span.
        assert data["urgent"] == pytest.approx(3 * 24 * 3600, abs=5)

    def test_reopened_bug_is_excluded(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        backdate_bug,
        days_ago,
    ):
        bug = make_bug(organization, project, admin_user, priority="medium")
        backdate_bug(bug, created_at=days_ago(5))
        bug = _walk_to(bug, admin_user, admin_membership, BugStatus.RESOLVED)
        backdate_bug(bug, resolved_at=days_ago(2))
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.REOPENED,
            expected_version=bug.version,
        )
        data = _resolution_time(admin_client, **_range(7))
        assert data["medium"] is None

    def test_reopened_then_resolved_again_uses_latest_resolved_at(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        backdate_bug,
        days_ago,
    ):
        """Documented Community behavior: duration is (current resolved_at -
        created_at), i.e. cumulative since original creation, not "time
        since reopened" — a deliberate simplicity trade-off (see Phase 5
        plan / docs/ACCESS_AND_TESTING.md)."""
        bug = make_bug(organization, project, admin_user, priority="low")
        backdate_bug(bug, created_at=days_ago(10))
        bug = _walk_to(bug, admin_user, admin_membership, BugStatus.RESOLVED)
        backdate_bug(bug, resolved_at=days_ago(6))
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
        backdate_bug(bug, resolved_at=days_ago(1))
        data = _resolution_time(admin_client, **_range(14))
        # 10 days ago -> 1 day ago is a 9-day span, not the 4-day span the
        # second resolution cycle alone would represent.
        assert data["low"] == pytest.approx(9 * 24 * 3600, abs=5)

    def test_closed_after_resolved_is_excluded(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        backdate_bug,
        days_ago,
    ):
        """CLOSED is terminal but not a RESOLUTION_STATUS — closing is a
        further step downstream of resolution, so a closed bug's current
        status is no longer "in RESOLUTION_STATUSES" and it drops out of
        this metric. Documented, not accidental."""
        bug = make_bug(organization, project, admin_user, priority="high")
        backdate_bug(bug, created_at=days_ago(5))
        bug = _walk_to(bug, admin_user, admin_membership, BugStatus.RESOLVED)
        backdate_bug(bug, resolved_at=days_ago(2))
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.CLOSED,
            expected_version=bug.version,
        )
        data = _resolution_time(admin_client, **_range(7))
        assert data["high"] is None

    def test_resolved_at_outside_range_is_excluded(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        backdate_bug,
        days_ago,
    ):
        bug = make_bug(organization, project, admin_user, priority="high")
        backdate_bug(bug, created_at=days_ago(40))
        bug = _walk_to(bug, admin_user, admin_membership, BugStatus.RESOLVED)
        backdate_bug(bug, resolved_at=days_ago(35))
        data = _resolution_time(admin_client, **_range(7))
        assert data["high"] is None

    def test_no_data_returns_null_not_zero(self, admin_client, project):
        data = _resolution_time(admin_client, **_range(7))
        assert data == {"urgent": None, "high": None, "medium": None, "low": None}

    def test_all_four_priorities_always_present(self, admin_client, project):
        data = _resolution_time(admin_client, **_range(7))
        assert set(data.keys()) == {"urgent", "high", "medium", "low"}

    def test_response_is_ordered_urgent_to_low(self, admin_client, project):
        response = admin_client.get(reverse("analytics-resolution-time"), _range(7))
        priorities = [row["priority"] for row in response.json()]
        assert priorities == ["urgent", "high", "medium", "low"]
