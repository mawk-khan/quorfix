import threading

import pytest
from django.db import close_old_connections

from apps.core.pg_advisory_lock import LockNotAcquired, advisory_lock

TEST_LOCK_KEY = 999_888_777_666_1


def run_concurrently(*targets):
    """Runs each target in its own thread with a fresh DB connection,
    releasing them together via a barrier — mirrors apps.organizations.
    tests.test_concurrency.run_concurrently (duplicated locally rather than
    imported cross-app, matching this codebase's general preference for
    test independence)."""
    barrier = threading.Barrier(len(targets))

    def wrap(target):
        def _run():
            barrier.wait()
            try:
                target()
            finally:
                close_old_connections()

        return _run

    threads = [threading.Thread(target=wrap(t)) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


@pytest.mark.django_db
class TestAdvisoryLockBasics:
    def test_acquires_and_releases(self):
        with advisory_lock(TEST_LOCK_KEY):
            pass
        # Released cleanly — acquiring again immediately must succeed.
        with advisory_lock(TEST_LOCK_KEY):
            pass

    def test_releases_even_on_exception(self):
        with pytest.raises(ValueError):
            with advisory_lock(TEST_LOCK_KEY):
                raise ValueError("boom")
        # Still released despite the exception.
        with advisory_lock(TEST_LOCK_KEY):
            pass


@pytest.mark.django_db(transaction=True)
class TestAdvisoryLockConcurrency:
    def test_second_concurrent_acquisition_is_refused(self):
        outcomes = []
        ready = threading.Event()
        release = threading.Event()

        def holder():
            with advisory_lock(TEST_LOCK_KEY):
                outcomes.append("held")
                ready.set()
                release.wait(timeout=5)

        def contender():
            ready.wait(timeout=5)
            try:
                with advisory_lock(TEST_LOCK_KEY):
                    outcomes.append("contender-acquired")
            except LockNotAcquired:
                outcomes.append("contender-refused")
            finally:
                release.set()

        run_concurrently(holder, contender)

        assert outcomes.count("held") == 1
        assert outcomes.count("contender-refused") == 1
        assert "contender-acquired" not in outcomes

        # Lock is free again once both threads finish.
        with advisory_lock(TEST_LOCK_KEY):
            pass
