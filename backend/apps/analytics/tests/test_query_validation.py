import datetime

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

RANGED_URL_NAMES = ["analytics-summary", "analytics-trends", "analytics-resolution-time"]
PROJECT_ONLY_URL_NAMES = [
    "analytics-distributions",
    "analytics-workload",
    "analytics-recent-activity",
]


def _today():
    from django.utils import timezone

    return timezone.localdate()


class TestRangedEndpointsRequireDates:
    @pytest.mark.parametrize("url_name", RANGED_URL_NAMES)
    def test_missing_date_from_is_rejected(self, admin_client, url_name):
        response = admin_client.get(reverse(url_name), {"date_to": str(_today())})
        assert response.status_code == 400
        assert "date_from" in response.json()

    @pytest.mark.parametrize("url_name", RANGED_URL_NAMES)
    def test_missing_date_to_is_rejected(self, admin_client, url_name):
        response = admin_client.get(reverse(url_name), {"date_from": str(_today())})
        assert response.status_code == 400
        assert "date_to" in response.json()

    @pytest.mark.parametrize("url_name", RANGED_URL_NAMES)
    def test_reversed_range_is_rejected(self, admin_client, url_name):
        today = _today()
        response = admin_client.get(
            reverse(url_name),
            {"date_from": str(today), "date_to": str(today - datetime.timedelta(days=1))},
        )
        assert response.status_code == 400
        assert "date_to" in response.json()

    @pytest.mark.parametrize("url_name", RANGED_URL_NAMES)
    def test_invalid_date_format_is_rejected(self, admin_client, url_name):
        response = admin_client.get(
            reverse(url_name), {"date_from": "not-a-date", "date_to": str(_today())}
        )
        assert response.status_code == 400

    @pytest.mark.parametrize("url_name", RANGED_URL_NAMES)
    def test_excessive_range_is_rejected(self, admin_client, url_name):
        today = _today()
        response = admin_client.get(
            reverse(url_name),
            {"date_from": str(today - datetime.timedelta(days=366)), "date_to": str(today)},
        )
        assert response.status_code == 400
        assert "date_to" in response.json()

    @pytest.mark.parametrize("url_name", RANGED_URL_NAMES)
    def test_366_day_range_is_the_max_allowed(self, admin_client, url_name):
        today = _today()
        response = admin_client.get(
            reverse(url_name),
            {"date_from": str(today - datetime.timedelta(days=365)), "date_to": str(today)},
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("url_name", RANGED_URL_NAMES)
    def test_same_day_range_is_valid(self, admin_client, url_name):
        today = _today()
        response = admin_client.get(
            reverse(url_name), {"date_from": str(today), "date_to": str(today)}
        )
        assert response.status_code == 200


class TestProjectOnlyEndpointsDoNotRequireDates:
    @pytest.mark.parametrize("url_name", PROJECT_ONLY_URL_NAMES)
    def test_no_query_params_required(self, admin_client, url_name):
        response = admin_client.get(reverse(url_name))
        assert response.status_code == 200

    def test_active_projects_requires_nothing_at_all(self, admin_client):
        response = admin_client.get(reverse("analytics-active-projects"))
        assert response.status_code == 200


class TestProjectFilterValidation:
    ALL_URL_NAMES = RANGED_URL_NAMES + PROJECT_ONLY_URL_NAMES

    def _params(self, url_name, project_value):
        today = _today()
        params = {"project": project_value}
        if url_name in RANGED_URL_NAMES:
            params.update({"date_from": str(today), "date_to": str(today)})
        return params

    @pytest.mark.parametrize("url_name", ALL_URL_NAMES)
    def test_malformed_project_uuid_is_rejected(self, admin_client, url_name):
        response = admin_client.get(reverse(url_name), self._params(url_name, "not-a-uuid"))
        assert response.status_code == 400
        assert "project" in response.json()

    @pytest.mark.parametrize("url_name", ALL_URL_NAMES)
    def test_foreign_org_project_is_rejected_non_enumerating(
        self, admin_client, url_name, other_project
    ):
        response = admin_client.get(
            reverse(url_name), self._params(url_name, str(other_project.pk))
        )
        assert response.status_code == 400
        assert "project" in response.json()

    @pytest.mark.parametrize("url_name", ALL_URL_NAMES)
    def test_unknown_project_uuid_gets_identical_error_shape(
        self, admin_client, url_name, other_project
    ):
        import uuid

        response_unknown = admin_client.get(
            reverse(url_name), self._params(url_name, str(uuid.uuid4()))
        )
        response_foreign = admin_client.get(
            reverse(url_name), self._params(url_name, str(other_project.pk))
        )
        # Non-enumerating: a truly nonexistent id and a real id belonging to
        # another organization must be indistinguishable to the caller.
        assert response_unknown.status_code == response_foreign.status_code == 400
        assert response_unknown.json() == response_foreign.json()

    @pytest.mark.parametrize("url_name", ALL_URL_NAMES)
    def test_own_project_uuid_is_accepted(self, admin_client, url_name, project):
        response = admin_client.get(reverse(url_name), self._params(url_name, str(project.pk)))
        assert response.status_code == 200


class TestAuthentication:
    @pytest.mark.parametrize(
        "url_name",
        RANGED_URL_NAMES + PROJECT_ONLY_URL_NAMES + ["analytics-active-projects"],
    )
    def test_anonymous_request_is_rejected(self, api_client, url_name):
        response = api_client.get(reverse(url_name))
        assert response.status_code in (401, 403)
