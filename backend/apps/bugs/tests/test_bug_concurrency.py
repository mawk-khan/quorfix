import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections

from apps.bugs.models import Bug
from apps.bugs.services import BugVersionConflict, create_bug, update_bug
from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
from apps.projects.models import Project, ProjectStatus

User = get_user_model()


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
def test_concurrent_updates_to_the_same_bug_only_one_wins():
    organization = Organization.objects.create(name="Acme", slug="acme-bug-concurrency")
    user = User.objects.create_user(
        username="conflict-admin", email="conflict@example.com", password="x"
    )
    membership = OrganizationMembership.objects.create(
        organization=organization, user=user, role=CommunityRole.ADMINISTRATOR
    )
    project = Project.objects.create(
        organization=organization, key="CFL", name="Conflict", status=ProjectStatus.ACTIVE
    )
    bug = create_bug(
        organization=organization,
        project=project,
        reporter=user,
        membership=membership,
        title="Race target",
    )
    starting_version = bug.version

    outcomes = []
    lock = threading.Lock()

    def attempt(title):
        try:
            update_bug(
                bug=bug,
                actor=user,
                membership=membership,
                expected_version=starting_version,
                title=title,
            )
            with lock:
                outcomes.append("ok")
        except BugVersionConflict:
            with lock:
                outcomes.append("conflict")

    run_concurrently(
        lambda: attempt("Title A"),
        lambda: attempt("Title B"),
    )

    assert outcomes.count("ok") == 1
    assert outcomes.count("conflict") == 1

    final = Bug.objects.get(pk=bug.pk)
    assert final.version == starting_version + 1
    assert final.title in ("Title A", "Title B")
