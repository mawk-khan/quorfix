import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.services import DEMO_ORGANIZATION_SLUG, DEMO_ROLE_TO_EMAIL
from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
from apps.organizations.services import (
    ProtectedDemoAccountError,
    change_member_role,
    create_invitation,
    remove_member,
)

# Step 3 (public-demo hardening) §3: the five seeded Quorfix Demo personas'
# role/membership must never change, and no sixth member may be added to
# the demo organization — regardless of who is asking, including the
# administrator-role demo persona itself. See apps.accounts.services.
# is_demo_user and apps.organizations.services.ProtectedDemoAccountError.


@pytest.fixture
def demo_organization(db):
    return Organization.objects.create(
        name="Quorfix Demo", slug=DEMO_ORGANIZATION_SLUG, is_active=False
    )


@pytest.fixture
def demo_admin(demo_organization, make_user, make_membership):
    user = make_user(DEMO_ROLE_TO_EMAIL[CommunityRole.ADMINISTRATOR])
    make_membership(demo_organization, user, role=CommunityRole.ADMINISTRATOR)
    return user


@pytest.fixture
def demo_developer(demo_organization, make_user, make_membership):
    user = make_user(DEMO_ROLE_TO_EMAIL[CommunityRole.DEVELOPER])
    make_membership(demo_organization, user, role=CommunityRole.DEVELOPER)
    return user


@pytest.fixture
def demo_admin_client(demo_admin):
    client = APIClient()
    client.force_login(demo_admin)
    return client


@pytest.mark.django_db
class TestServiceLayerProtection:
    def test_change_member_role_refuses_a_demo_persona_target(
        self, demo_organization, demo_admin, demo_developer
    ):
        membership = OrganizationMembership.objects.get(
            organization=demo_organization, user=demo_developer
        )
        with pytest.raises(ProtectedDemoAccountError):
            change_member_role(membership=membership, new_role=CommunityRole.ADMINISTRATOR)
        membership.refresh_from_db()
        assert membership.role == CommunityRole.DEVELOPER

    def test_change_member_role_refuses_even_when_actor_would_be_the_admin_persona(
        self, demo_organization, demo_admin
    ):
        # The admin persona attempting to demote *itself* — still refused,
        # not merely because it would leave zero administrators (that's a
        # separate, pre-existing guard) but because it's a protected demo
        # account at all.
        membership = OrganizationMembership.objects.get(
            organization=demo_organization, user=demo_admin
        )
        with pytest.raises(ProtectedDemoAccountError):
            change_member_role(membership=membership, new_role=CommunityRole.VIEWER)

    def test_remove_member_refuses_a_demo_persona_target(
        self, demo_organization, demo_admin, demo_developer
    ):
        membership = OrganizationMembership.objects.get(
            organization=demo_organization, user=demo_developer
        )
        with pytest.raises(ProtectedDemoAccountError):
            remove_member(membership=membership)
        assert OrganizationMembership.objects.filter(pk=membership.pk).exists()

    def test_create_invitation_refuses_for_the_demo_organization(
        self, demo_organization, demo_admin
    ):
        with pytest.raises(ProtectedDemoAccountError):
            create_invitation(
                organization=demo_organization,
                invited_by=demo_admin,
                email="newcomer@example.com",
                role=CommunityRole.VIEWER,
            )
        assert not OrganizationMembership.objects.filter(
            organization=demo_organization, user__email="newcomer@example.com"
        ).exists()

    def test_bypass_demo_protection_is_available_only_to_an_explicit_trusted_caller(
        self, demo_organization, demo_admin, demo_developer
    ):
        # apps.core.management.commands.seed_demo is the one caller that
        # legitimately needs this — never reachable from any view/serializer.
        membership = OrganizationMembership.objects.get(
            organization=demo_organization, user=demo_developer
        )
        updated = change_member_role(
            membership=membership, new_role=CommunityRole.QA, bypass_demo_protection=True
        )
        assert updated.role == CommunityRole.QA

        invitation, _raw_token = create_invitation(
            organization=demo_organization,
            invited_by=demo_admin,
            email="seed-only@example.com",
            role=CommunityRole.VIEWER,
            bypass_demo_protection=True,
        )
        assert invitation.email == "seed-only@example.com"

    def test_ordinary_organization_is_unaffected(
        self, organization, admin_membership, make_user, make_membership
    ):
        # Regression guard: the protection is scoped to the "quorfix-demo"
        # slug specifically — normal Community role/membership management
        # keeps working exactly as before (also covered end-to-end by
        # test_memberships.py, unmodified by this change).
        developer = make_user("dev@example.com")
        membership = make_membership(organization, developer, role=CommunityRole.DEVELOPER)
        updated = change_member_role(membership=membership, new_role=CommunityRole.QA)
        assert updated.role == CommunityRole.QA
        remove_member(membership=updated)
        assert not OrganizationMembership.objects.filter(pk=membership.pk).exists()


@pytest.mark.django_db
class TestMembershipApiProtection:
    def test_admin_persona_cannot_change_another_personas_role(
        self, demo_admin_client, demo_organization, demo_developer
    ):
        membership = OrganizationMembership.objects.get(
            organization=demo_organization, user=demo_developer
        )
        response = demo_admin_client.patch(
            f"/api/members/{membership.pk}/", {"role": "administrator"}
        )
        assert response.status_code == 403
        membership.refresh_from_db()
        assert membership.role == CommunityRole.DEVELOPER

    def test_admin_persona_cannot_remove_another_persona(
        self, demo_admin_client, demo_organization, demo_developer
    ):
        membership = OrganizationMembership.objects.get(
            organization=demo_organization, user=demo_developer
        )
        response = demo_admin_client.delete(f"/api/members/{membership.pk}/")
        assert response.status_code == 403
        assert OrganizationMembership.objects.filter(pk=membership.pk).exists()

    def test_admin_persona_cannot_invite_a_new_member(self, demo_admin_client):
        response = demo_admin_client.post(
            "/api/invitations/", {"email": "newcomer@example.com", "role": "viewer"}
        )
        assert response.status_code == 403
        assert not OrganizationMembership.objects.filter(
            user__email="newcomer@example.com"
        ).exists()
        # Blocked before apps.organizations.views.InvitationViewSet.create
        # ever reaches its send_mail() call — no email attempted at all,
        # not merely a rewritten/sunk one.
        assert len(mail.outbox) == 0

    def test_rejection_response_reveals_no_account_detail(
        self, demo_admin_client, demo_organization, demo_developer
    ):
        membership = OrganizationMembership.objects.get(
            organization=demo_organization, user=demo_developer
        )
        response = demo_admin_client.delete(f"/api/members/{membership.pk}/")
        body = response.content.decode().lower()
        assert "demo" not in body
        assert "quorfix-demo" not in body
