import threading

import pytest
from django.db import close_old_connections

from apps.organizations.models import Organization
from apps.projects.models import Project
from apps.projects.services import DuplicateProjectKey, create_project


def run_concurrently(*targets):
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


@pytest.mark.django_db(transaction=True)
def test_concurrent_create_with_the_same_key_only_one_succeeds():
    organization = Organization.objects.create(name="Acme", slug="acme")
    outcomes = []

    def attempt(name):
        try:
            create_project(organization=organization, name=name, key="ENG")
            outcomes.append("ok")
        except DuplicateProjectKey:
            outcomes.append("blocked")

    run_concurrently(
        lambda: attempt("Engine A"),
        lambda: attempt("Engine B"),
    )

    assert outcomes.count("ok") == 1
    assert outcomes.count("blocked") == 1
    assert Project.objects.filter(organization=organization, key="ENG").count() == 1
