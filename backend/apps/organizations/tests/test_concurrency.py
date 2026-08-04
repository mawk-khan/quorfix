import threading

import pytest
from django.db import close_old_connections
from django.utils import timezone

from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
from apps.organizations.services import (
    LastAdministratorError,
    SetupAlreadyCompleted,
    SetupNotAllowed,
    accept_invitation,
    change_member_role,
    create_invitation,
    remove_member,
    setup_instance,
)


def run_concurrently(*targets):
    """Runs each target in its own thread, releasing them together, and
    waits for all to finish. Each target must close its own DB connection
    when done (a fresh connection per thread is required for real
    select_for_update() contention to be observable)."""
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
def test_concurrent_setup_double_submit_only_one_organization_is_created(password):
    outcomes = []

    def attempt(email):
        try:
            setup_instance(organization_name="Acme", email=email, password=password)
            outcomes.append("ok")
        except (SetupAlreadyCompleted, SetupNotAllowed):
            outcomes.append("blocked")

    run_concurrently(
        lambda: attempt("admin-a@example.com"),
        lambda: attempt("admin-b@example.com"),
    )

    assert outcomes.count("ok") == 1
    assert outcomes.count("blocked") == 1
    assert Organization.objects.count() == 1
    assert OrganizationMembership.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_invitation_accept_only_one_membership_is_created():
    organization = Organization.objects.create(name="Acme", slug="acme")
    from django.contrib.auth import get_user_model

    admin = get_user_model().objects.create_user(
        username="admin", email="admin@example.com", password="irrelevant"
    )
    invitation, raw_token = create_invitation(
        organization=organization, invited_by=admin, email="new@example.com", role="developer"
    )

    outcomes = []

    def attempt(password):
        try:
            accept_invitation(raw_token=raw_token, password=password)
            outcomes.append("ok")
        except Exception:  # noqa: BLE001 - any failure means "blocked" for this race
            outcomes.append("blocked")

    run_concurrently(
        lambda: attempt("password-a!"),
        lambda: attempt("password-b!"),
    )

    assert outcomes.count("ok") == 1
    memberships = OrganizationMembership.objects.filter(
        organization=organization, user__email="new@example.com"
    )
    assert memberships.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_demotion_of_two_administrators_leaves_at_least_one():
    organization = Organization.objects.create(name="Acme", slug="acme")
    from django.contrib.auth import get_user_model

    User = get_user_model()
    admin_a = User.objects.create_user(username="a", email="a@example.com", password="x")
    admin_b = User.objects.create_user(username="b", email="b@example.com", password="x")
    membership_a = OrganizationMembership.objects.create(
        organization=organization,
        user=admin_a,
        role=CommunityRole.ADMINISTRATOR,
        joined_at=timezone.now(),
    )
    membership_b = OrganizationMembership.objects.create(
        organization=organization,
        user=admin_b,
        role=CommunityRole.ADMINISTRATOR,
        joined_at=timezone.now(),
    )

    outcomes = []

    def demote(membership):
        try:
            change_member_role(membership=membership, new_role=CommunityRole.DEVELOPER)
            outcomes.append("ok")
        except LastAdministratorError:
            outcomes.append("blocked")

    run_concurrently(
        lambda: demote(membership_a),
        lambda: demote(membership_b),
    )

    remaining_admins = OrganizationMembership.objects.filter(
        organization=organization, role=CommunityRole.ADMINISTRATOR
    ).count()
    assert remaining_admins >= 1
    assert outcomes.count("blocked") >= 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_removal_of_two_administrators_leaves_at_least_one():
    organization = Organization.objects.create(name="Acme", slug="acme")
    from django.contrib.auth import get_user_model

    User = get_user_model()
    admin_a = User.objects.create_user(username="a", email="a@example.com", password="x")
    admin_b = User.objects.create_user(username="b", email="b@example.com", password="x")
    membership_a = OrganizationMembership.objects.create(
        organization=organization,
        user=admin_a,
        role=CommunityRole.ADMINISTRATOR,
        joined_at=timezone.now(),
    )
    membership_b = OrganizationMembership.objects.create(
        organization=organization,
        user=admin_b,
        role=CommunityRole.ADMINISTRATOR,
        joined_at=timezone.now(),
    )

    outcomes = []

    def remove(membership):
        try:
            remove_member(membership=membership)
            outcomes.append("ok")
        except LastAdministratorError:
            outcomes.append("blocked")

    run_concurrently(
        lambda: remove(membership_a),
        lambda: remove(membership_b),
    )

    remaining_admins = OrganizationMembership.objects.filter(
        organization=organization, role=CommunityRole.ADMINISTRATOR
    ).count()
    assert remaining_admins >= 1
    assert outcomes.count("blocked") >= 1
