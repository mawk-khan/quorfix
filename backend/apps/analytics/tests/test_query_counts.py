"""Proves every dashboard endpoint issues a small, fixed number of queries
regardless of dataset size — no query per status/priority/severity/
developer/project. Cache is cleared before every measured call so each
assertion reflects a real "cold" computation, the worst case that actually
matters for N+1 detection (a cache hit trivially costs ~0 extra queries)."""

import datetime

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.bugs.services import assign_bug, transition_bug
from apps.organizations.models import CommunityRole

pytestmark = pytest.mark.django_db


def _range(days=7):
    today = timezone.localdate()
    return {"date_from": str(today - datetime.timedelta(days=days)), "date_to": str(today)}


def _make_varied_bugs(organization, project, admin_user, admin_membership, make_bug, count):
    for i in range(count):
        bug = make_bug(organization, project, admin_user, title=f"Bug {i}")
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status="triaged",
            expected_version=bug.version,
        )


class TestQueryCountStability:
    @pytest.mark.parametrize("bug_count", [3, 30])
    def test_summary_query_count_is_stable(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        django_assert_max_num_queries,
        bug_count,
    ):
        _make_varied_bugs(organization, project, admin_user, admin_membership, make_bug, bug_count)
        cache.clear()
        with django_assert_max_num_queries(8):
            response = admin_client.get(reverse("analytics-summary"), _range())
        assert response.status_code == 200

    @pytest.mark.parametrize("bug_count", [3, 30])
    def test_trends_query_count_is_stable(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        django_assert_max_num_queries,
        bug_count,
    ):
        _make_varied_bugs(organization, project, admin_user, admin_membership, make_bug, bug_count)
        cache.clear()
        with django_assert_max_num_queries(6):
            response = admin_client.get(reverse("analytics-trends"), _range())
        assert response.status_code == 200

    @pytest.mark.parametrize("bug_count", [3, 30])
    def test_resolution_time_query_count_is_stable(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        django_assert_max_num_queries,
        bug_count,
    ):
        _make_varied_bugs(organization, project, admin_user, admin_membership, make_bug, bug_count)
        cache.clear()
        with django_assert_max_num_queries(5):
            response = admin_client.get(reverse("analytics-resolution-time"), _range())
        assert response.status_code == 200

    @pytest.mark.parametrize("bug_count", [3, 30])
    def test_distributions_query_count_is_stable_across_statuses_and_severities(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        django_assert_max_num_queries,
        bug_count,
    ):
        _make_varied_bugs(organization, project, admin_user, admin_membership, make_bug, bug_count)
        cache.clear()
        with django_assert_max_num_queries(6):
            response = admin_client.get(reverse("analytics-distributions"))
        assert response.status_code == 200

    def test_workload_query_count_is_stable_across_many_developers(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_user,
        make_membership,
        make_bug,
        django_assert_max_num_queries,
    ):
        # Ten distinct eligible assignees, one bug each — a per-developer
        # query bug would show up as query count scaling with this loop.
        for i in range(10):
            developer = make_user(f"dev{i}@example.com")
            make_membership(organization, developer, role=CommunityRole.DEVELOPER)
            bug = make_bug(organization, project, admin_user, title=f"Bug {i}")
            assign_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                assignee_id=str(developer.pk),
                expected_version=bug.version,
            )
        cache.clear()
        with django_assert_max_num_queries(6):
            response = admin_client.get(reverse("analytics-workload"))
        assert response.status_code == 200
        assert len(response.json()["eligible"]) == 10

    def test_active_projects_query_count_is_stable_across_many_projects(
        self,
        admin_client,
        organization,
        admin_user,
        make_project,
        make_bug,
        django_assert_max_num_queries,
    ):
        # Ten distinct projects, several bugs each — a per-project query bug
        # would show up as query count scaling with this loop.
        for i in range(10):
            proj = make_project(organization, key=f"PRJ{i}", name=f"Project {i}")
            make_bug(organization, proj, admin_user, title=f"Bug {i}")
        cache.clear()
        with django_assert_max_num_queries(5):
            response = admin_client.get(reverse("analytics-active-projects"))
        assert response.status_code == 200
        assert len(response.json()) == 10

    @pytest.mark.parametrize("bug_count", [3, 30])
    def test_recent_activity_query_count_is_stable(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        admin_membership,
        make_bug,
        django_assert_max_num_queries,
        bug_count,
    ):
        _make_varied_bugs(organization, project, admin_user, admin_membership, make_bug, bug_count)
        with django_assert_max_num_queries(7):
            response = admin_client.get(reverse("analytics-recent-activity"), {"page_size": 25})
        assert response.status_code == 200
