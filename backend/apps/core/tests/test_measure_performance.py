import io
import json
import os
import tempfile

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def _generate_tiny_dataset():
    previous = os.environ.get("QUORFIX_DISPOSABLE_DATABASE")
    os.environ["QUORFIX_DISPOSABLE_DATABASE"] = "true"
    try:
        call_command(
            "generate_perf_dataset",
            "--seed",
            "9",
            "--organizations",
            "1",
            "--projects-per-organization",
            "1",
            "--users-per-organization",
            "3",
            "--bugs-per-organization",
            "12",
            "--comments-per-bug",
            "2",
            "--attachment-rate",
            "1.0",
            stdout=io.StringIO(),
        )
    finally:
        if previous is None:
            os.environ.pop("QUORFIX_DISPOSABLE_DATABASE", None)
        else:
            os.environ["QUORFIX_DISPOSABLE_DATABASE"] = previous


@pytest.mark.django_db
def test_refuses_when_no_perf_organization_exists():
    with pytest.raises(CommandError, match="generate_perf_dataset"):
        call_command("measure_performance", "--runs", "1", "--warmup-runs", "0")


@pytest.mark.django_db
def test_writes_valid_json_output_with_expected_shape():
    _generate_tiny_dataset()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        output_path = tmp.name

    call_command(
        "measure_performance",
        "--runs",
        "2",
        "--warmup-runs",
        "0",
        "--scenario",
        "bugs-first-page",
        "--output",
        output_path,
        stdout=io.StringIO(),
    )

    with open(output_path) as fh:
        report = json.load(fh)

    assert report["organization"].startswith("perf-")
    assert len(report["scenarios"]) == 1
    scenario = report["scenarios"][0]
    assert scenario["name"] == "bugs-first-page"
    assert scenario["sample_count"] == 2
    assert scenario["status_codes"] == [200]
    for key in ("median", "min", "max"):
        assert scenario["duration_ms"][key] >= 0
    assert scenario["query_count"]["median"] >= 1
    assert scenario["response_bytes"]["median"] > 0


@pytest.mark.django_db
def test_redis_unavailable_scenario_still_returns_200_via_fallback():
    _generate_tiny_dataset()
    out = io.StringIO()
    call_command(
        "measure_performance",
        "--runs",
        "1",
        "--warmup-runs",
        "0",
        "--scenario",
        "analytics-summary-redis-unavailable",
        stdout=out,
    )
    # cache_or_compute's own fallback (apps.analytics.caching) is what makes
    # this assertion meaningful: the view must still succeed even though the
    # cache backend for this one scenario is deliberately pointed at an
    # unreachable Redis.
    assert "status=[200]" in out.getvalue()


@pytest.mark.django_db
def test_invalid_scenario_name_raises_command_error():
    _generate_tiny_dataset()
    with pytest.raises(CommandError, match="Unknown scenario"):
        call_command(
            "measure_performance",
            "--runs",
            "1",
            "--warmup-runs",
            "0",
            "--scenario",
            "not-a-real-scenario",
        )


@pytest.mark.django_db
def test_include_sql_reports_slowest_queries():
    _generate_tiny_dataset()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        output_path = tmp.name

    call_command(
        "measure_performance",
        "--runs",
        "1",
        "--warmup-runs",
        "0",
        "--scenario",
        "bugs-first-page",
        "--include-sql",
        "--output",
        output_path,
        stdout=io.StringIO(),
    )

    with open(output_path) as fh:
        report = json.load(fh)

    slow = report["scenarios"][0]["slowest_queries"]
    assert len(slow) >= 1
    assert "sql" in slow[0] and "time_ms" in slow[0]


@pytest.mark.django_db
def test_organization_flag_selects_a_specific_perf_organization():
    _generate_tiny_dataset()
    from apps.core.management.commands.generate_perf_dataset import PERF_SLUG_PREFIX
    from apps.organizations.models import Organization

    org = Organization.objects.get(slug__startswith=PERF_SLUG_PREFIX)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        output_path = tmp.name

    call_command(
        "measure_performance",
        "--organization",
        org.slug,
        "--runs",
        "1",
        "--warmup-runs",
        "0",
        "--scenario",
        "bugs-first-page",
        "--output",
        output_path,
        stdout=io.StringIO(),
    )

    with open(output_path) as fh:
        report = json.load(fh)
    assert report["organization"] == org.slug


@pytest.mark.django_db
def test_unknown_organization_slug_raises_command_error():
    _generate_tiny_dataset()
    with pytest.raises(CommandError, match="perf-owned organization"):
        call_command(
            "measure_performance",
            "--organization",
            "perf-does-not-exist",
            "--runs",
            "1",
            "--warmup-runs",
            "0",
        )
