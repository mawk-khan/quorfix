import pytest

from apps.organizations.models import SetupLock


@pytest.fixture(autouse=True)
def _setup_lock_seeded(db):
    """SetupLock's singleton row is normally seeded once, when the test
    database is first created, by a data migration. Any `transaction=True`
    test anywhere in the suite flushes the database afterward to reset
    state for the next test — and flush does not re-run data migrations —
    so that row can be gone by the time a test in this file needs it,
    depending entirely on pytest's test collection order across the whole
    suite (alphabetically, apps.bugs's own transaction=True tests now run
    before apps.organizations's). Re-seeding it here, scoped to just this
    test package, removes that cross-file ordering hazard without touching
    the tests that actually exercise SetupLock's behavior.
    """
    SetupLock.objects.get_or_create(id=1)
