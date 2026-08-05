import datetime
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analytics import caching, selectors
from apps.analytics.caching import cache_or_compute

pytestmark = pytest.mark.django_db


def _range(days=7):
    today = timezone.localdate()
    return {"date_from": str(today - datetime.timedelta(days=days)), "date_to": str(today)}


# -- unit-level: cache_or_compute itself -------------------------------


class TestCacheOrComputeUnit:
    def test_miss_computes_and_stores(self):
        cache.clear()
        calls = []

        def compute():
            calls.append(1)
            return {"value": 42}

        result = cache_or_compute("test:key:v1", compute)
        assert result == {"value": 42}
        assert len(calls) == 1
        assert cache.get("test:key:v1") == {"value": 42}

    def test_hit_does_not_call_compute(self):
        cache.clear()
        cache.set("test:key:v1", {"value": "cached"}, 60)
        calls = []

        def compute():
            calls.append(1)
            return {"value": "fresh"}

        result = cache_or_compute("test:key:v1", compute)
        assert result == {"value": "cached"}
        assert len(calls) == 0

    def test_read_failure_falls_back_to_compute(self):
        def compute():
            return {"value": "computed"}

        with patch.object(caching.cache, "get", side_effect=Exception("redis down")):
            result = cache_or_compute("test:key:v1", compute)
        assert result == {"value": "computed"}

    def test_read_failure_logs_a_warning(self, caplog):
        def compute():
            return {"value": "computed"}

        with patch.object(caching.cache, "get", side_effect=Exception("redis down")):
            with caplog.at_level("WARNING"):
                cache_or_compute("test:key:v1", compute)
        assert "Analytics cache read failed" in caplog.text

    def test_write_failure_still_returns_correct_data(self):
        cache.clear()

        def compute():
            return {"value": "computed"}

        with patch.object(caching.cache, "set", side_effect=Exception("redis down")):
            result = cache_or_compute("test:key:v1", compute)
        assert result == {"value": "computed"}

    def test_ttl_is_configurable_via_settings(self, settings):
        cache.clear()
        settings.ANALYTICS_CACHE_TTL_SECONDS = 5
        with patch.object(caching.cache, "set") as mocked_set:
            cache_or_compute("test:key:v1", lambda: {"value": 1})
        assert mocked_set.call_args.args[2] == 5


# -- integration-level: endpoints actually use the cache -----------------


class TestEndpointCaching:
    def test_second_call_within_ttl_does_not_recompute(self, admin_client, project):
        original = selectors.status_distribution
        with patch("apps.analytics.views.selectors.status_distribution", wraps=original) as mocked:
            admin_client.get(reverse("analytics-distributions"))
            admin_client.get(reverse("analytics-distributions"))
        assert mocked.call_count == 1

    def test_summary_result_matches_between_cached_and_uncached_calls(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user)
        first = admin_client.get(reverse("analytics-summary"), _range()).json()
        second = admin_client.get(reverse("analytics-summary"), _range()).json()
        assert first == second

    def test_recent_activity_recomputes_on_every_call(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user)
        original = selectors.recent_activity
        with patch("apps.analytics.views.selectors.recent_activity", wraps=original) as mocked:
            admin_client.get(reverse("analytics-recent-activity"))
            admin_client.get(reverse("analytics-recent-activity"))
        assert mocked.call_count == 2

    def test_distributions_cache_key_ignores_irrelevant_date_params(self, admin_client, project):
        original = selectors.status_distribution
        with patch("apps.analytics.views.selectors.status_distribution", wraps=original) as mocked:
            admin_client.get(
                reverse("analytics-distributions"),
                {"date_from": "2020-01-01", "date_to": "2020-01-02"},
            )
            admin_client.get(
                reverse("analytics-distributions"),
                {"date_from": "2021-06-01", "date_to": "2021-06-05"},
            )
        assert mocked.call_count == 1

    def test_workload_cache_key_ignores_irrelevant_date_params(self, admin_client, project):
        original = selectors.workload
        with patch("apps.analytics.views.selectors.workload", wraps=original) as mocked:
            admin_client.get(reverse("analytics-workload"), {"date_from": "2020-01-01"})
            admin_client.get(reverse("analytics-workload"), {"date_from": "2022-01-01"})
        assert mocked.call_count == 1

    def test_a_failing_cache_backend_still_serves_correct_dashboard_data(
        self, admin_client, organization, project, admin_user, make_bug
    ):
        make_bug(organization, project, admin_user)
        with patch.object(caching.cache, "get", side_effect=Exception("redis down")):
            with patch.object(caching.cache, "set", side_effect=Exception("redis down")):
                response = admin_client.get(reverse("analytics-summary"), _range())
        assert response.status_code == 200
        assert response.json()["open_bugs"] == 1


class TestCacheKeyIsolation:
    def test_isolated_between_organizations(
        self,
        admin_client,
        organization,
        project,
        admin_user,
        make_bug,
        other_organization,
        other_admin_user,
        other_admin_membership,
        other_project,
    ):
        make_bug(organization, project, admin_user, title="Org A bug")

        other_client = APIClient()
        other_client.force_login(other_admin_user)
        make_bug(other_organization, other_project, other_admin_user, title="Org B bug 1")
        make_bug(other_organization, other_project, other_admin_user, title="Org B bug 2")

        data_a = admin_client.get(reverse("analytics-summary"), _range()).json()
        data_b = other_client.get(reverse("analytics-summary"), _range()).json()

        assert data_a["open_bugs"] == 1
        assert data_b["open_bugs"] == 2

    def test_isolated_between_projects_within_same_organization(
        self, admin_client, organization, project, make_project, admin_user, make_bug
    ):
        other = make_project(organization, key="OTH9", name="Other")
        make_bug(organization, project, admin_user)
        make_bug(organization, other, admin_user)
        make_bug(organization, other, admin_user)

        data_project = admin_client.get(
            reverse("analytics-summary"), {**_range(), "project": str(project.pk)}
        ).json()
        data_other = admin_client.get(
            reverse("analytics-summary"), {**_range(), "project": str(other.pk)}
        ).json()
        data_all = admin_client.get(reverse("analytics-summary"), _range()).json()

        assert data_project["open_bugs"] == 1
        assert data_other["open_bugs"] == 2
        assert data_all["open_bugs"] == 3

    def test_isolated_between_date_ranges(
        self, admin_client, organization, project, admin_user, make_bug, backdate_bug, days_ago
    ):
        recent = make_bug(organization, project, admin_user, title="Recent")
        backdate_bug(recent, created_at=days_ago(2))
        old = make_bug(organization, project, admin_user, title="Old")
        backdate_bug(old, created_at=days_ago(20))

        narrow = admin_client.get(reverse("analytics-summary"), _range(3)).json()
        wide = admin_client.get(reverse("analytics-summary"), _range(30)).json()

        assert narrow["new_bugs"] == 1
        assert wide["new_bugs"] == 2
