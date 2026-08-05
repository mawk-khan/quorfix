"""Shared fixtures for apps.analytics tests.

Backdating uses queryset .update() rather than instance.save() — the same
technique documented in apps.analytics.selectors and used by seed_demo:
auto_now_add / auto-stamped fields only re-stamp on .save(), not on
.update(), so this is the only way to give a test bug a historical
timestamp while still creating it through the real service layer.
"""

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.activities.models import BugActivity
from apps.bugs.models import Bug
from apps.organizations.models import CommunityRole, Organization


@pytest.fixture
def backdate_bug():
    def _backdate(bug, *, created_at=None, resolved_at=None, closed_at=None, due_date=None):
        updates = {}
        if created_at is not None:
            updates["created_at"] = created_at
        if resolved_at is not None:
            updates["resolved_at"] = resolved_at
        if closed_at is not None:
            updates["closed_at"] = closed_at
        if due_date is not None:
            updates["due_date"] = due_date
        if updates:
            Bug.objects.filter(pk=bug.pk).update(**updates)
            bug.refresh_from_db()
        return bug

    return _backdate


@pytest.fixture
def backdate_activity():
    def _backdate(bug, *, verb, to_value, created_at):
        BugActivity.objects.filter(bug=bug, verb=verb, to_value=to_value).update(
            created_at=created_at
        )

    return _backdate


@pytest.fixture
def days_ago():
    def _days_ago(n: int) -> datetime.datetime:
        return timezone.now() - datetime.timedelta(days=n)

    return _days_ago


@pytest.fixture
def other_organization(db):
    return Organization.objects.create(name="Other Org", slug="other-org")


@pytest.fixture
def other_admin_user(make_user):
    return make_user("other-admin@example.com")


@pytest.fixture
def other_admin_membership(other_organization, other_admin_user, make_membership):
    return make_membership(other_organization, other_admin_user, role=CommunityRole.ADMINISTRATOR)


@pytest.fixture
def other_project(other_organization, make_project):
    return make_project(other_organization, key="OTH", name="Other Project")


@pytest.fixture(autouse=True)
def _clear_analytics_cache():
    """Redis-backed cache is a real shared backend across tests, unlike the
    per-test Postgres transaction rollback — without this, a stale key from
    an earlier test could (in principle) be read by a later one. Cache keys
    are already org/project-scoped by a fresh UUID per test, so this isn't a
    correctness bug today, but clearing explicitly keeps caching tests
    deterministic and keeps the Redis test database from accumulating keys
    across repeated local test runs."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
