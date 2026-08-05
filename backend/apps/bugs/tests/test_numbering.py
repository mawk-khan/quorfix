import threading

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone

from apps.bugs.models import Bug
from apps.bugs.services import ProjectArchivedForBugCreation, create_bug
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


@pytest.mark.django_db
class TestNumbering:
    def test_sequential_numbers_within_a_project(
        self, organization, project, admin_user, admin_membership
    ):
        first = create_bug(
            organization=organization,
            project=project,
            reporter=admin_user,
            membership=admin_membership,
            title="First",
        )
        second = create_bug(
            organization=organization,
            project=project,
            reporter=admin_user,
            membership=admin_membership,
            title="Second",
        )
        assert first.number == 1
        assert second.number == 2
        assert first.key == f"{project.key}-1"
        assert second.key == f"{project.key}-2"

    def test_independent_sequences_across_projects(
        self, organization, make_project, admin_user, admin_membership
    ):
        project_a = make_project(organization, key="AAA", name="Project A")
        project_b = make_project(organization, key="BBB", name="Project B")

        a1 = create_bug(
            organization=organization,
            project=project_a,
            reporter=admin_user,
            membership=admin_membership,
            title="A1",
        )
        b1 = create_bug(
            organization=organization,
            project=project_b,
            reporter=admin_user,
            membership=admin_membership,
            title="B1",
        )
        a2 = create_bug(
            organization=organization,
            project=project_a,
            reporter=admin_user,
            membership=admin_membership,
            title="A2",
        )

        assert (a1.number, a1.key) == (1, "AAA-1")
        assert (b1.number, b1.key) == (1, "BBB-1")
        assert (a2.number, a2.key) == (2, "AAA-2")

    def test_counter_does_not_advance_when_creation_rolls_back(
        self, organization, project, admin_user, admin_membership
    ):
        """title=None fails the column's NOT NULL constraint inside
        Bug.objects.create() — which runs *after* the project counter is
        incremented and saved in the same @transaction.atomic function —
        so this exercises a genuine rollback of an already-incremented
        counter, not just a pre-increment validation failure."""
        starting_counter = Project.objects.get(pk=project.pk).next_bug_number

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                create_bug(
                    organization=organization,
                    project=project,
                    reporter=admin_user,
                    membership=admin_membership,
                    title=None,
                )

        assert Project.objects.get(pk=project.pk).next_bug_number == starting_counter
        assert not Bug.objects.filter(project=project).exists()

    def test_archived_project_blocks_creation_and_does_not_advance_counter(
        self, organization, project, admin_user, admin_membership
    ):
        project.archived_at = timezone.now()
        project.save(update_fields=["archived_at"])
        starting_counter = project.next_bug_number

        with pytest.raises(ProjectArchivedForBugCreation):
            create_bug(
                organization=organization,
                project=project,
                reporter=admin_user,
                membership=admin_membership,
                title="Should not be created",
            )

        assert Project.objects.get(pk=project.pk).next_bug_number == starting_counter
        assert not Bug.objects.filter(project=project).exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_creates_in_the_same_project_get_unique_sequential_numbers():
    organization = Organization.objects.create(name="Acme", slug="acme-numbering")
    user = User.objects.create_user(
        username="numbering-admin", email="numbering@example.com", password="x"
    )
    membership = OrganizationMembership.objects.create(
        organization=organization, user=user, role=CommunityRole.ADMINISTRATOR
    )
    project = Project.objects.create(
        organization=organization, key="CNC", name="Concurrency", status=ProjectStatus.ACTIVE
    )

    outcomes = []
    lock = threading.Lock()

    def attempt(title):
        bug = create_bug(
            organization=organization,
            project=project,
            reporter=user,
            membership=membership,
            title=title,
        )
        with lock:
            outcomes.append(bug.number)

    run_concurrently(*[lambda t=f"Bug {i}": attempt(t) for i in range(8)])

    assert sorted(outcomes) == list(range(1, 9))
    assert Project.objects.get(pk=project.pk).next_bug_number == 9
