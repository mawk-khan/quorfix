from datetime import timedelta

import pytest
from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.organizations.models import (
    CommunityRole,
    Invitation,
    Organization,
    OrganizationMembership,
)
from apps.organizations.services import create_invitation


@pytest.mark.django_db
class TestInvitationCreate:
    def test_requires_admin(
        self, api_client, organization, make_user, make_membership, admin_membership
    ):
        developer_user = make_user("dev@example.com")
        make_membership(organization, developer_user, role=CommunityRole.DEVELOPER)
        api_client.force_login(developer_user)

        response = api_client.post(
            "/api/invitations/", {"email": "new@example.com", "role": "developer"}
        )
        assert response.status_code == 403

    def test_repeated_invitation_creation_is_throttled(
        self, admin_client, organization, monkeypatch
    ):
        # Same technique as apps.accounts.tests.test_auth's login-throttle
        # test — see that test's comment for why monkeypatch.setitem (not
        # override_settings) is what actually reaches ScopedRateThrottle.
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "invitation-create", "1/min")
        cache.clear()
        first = admin_client.post(
            "/api/invitations/", {"email": "first@example.com", "role": "developer"}
        )
        second = admin_client.post(
            "/api/invitations/", {"email": "second@example.com", "role": "developer"}
        )
        assert first.status_code == 201
        assert second.status_code == 429

    def test_admin_can_invite_and_receives_invite_url(self, admin_client, organization):
        response = admin_client.post(
            "/api/invitations/", {"email": "new@example.com", "role": "developer"}
        )
        assert response.status_code == 201
        assert "invite_url" in response.json()
        assert Invitation.objects.filter(
            organization=organization, email="new@example.com"
        ).exists()
        assert len(mail.outbox) == 1
        assert "new@example.com" in mail.outbox[0].to

    def test_rejects_duplicate_pending_invitation(self, admin_client, organization, admin_user):
        create_invitation(
            organization=organization,
            invited_by=admin_user,
            email="new@example.com",
            role="developer",
        )
        response = admin_client.post(
            "/api/invitations/", {"email": "new@example.com", "role": "viewer"}
        )
        assert response.status_code == 409

    def test_rejects_inviting_an_existing_member(self, admin_client, admin_user):
        response = admin_client.post(
            "/api/invitations/", {"email": admin_user.email, "role": "developer"}
        )
        assert response.status_code == 409


@pytest.mark.django_db
class TestInvitationListAndCancel:
    def test_list_requires_admin(
        self, api_client, organization, make_user, make_membership, admin_membership
    ):
        developer_user = make_user("dev@example.com")
        make_membership(organization, developer_user, role=CommunityRole.DEVELOPER)
        api_client.force_login(developer_user)

        response = api_client.get("/api/invitations/")
        assert response.status_code == 403

    def test_admin_can_cancel_a_pending_invitation(self, admin_client, organization, admin_user):
        invitation, _token = create_invitation(
            organization=organization,
            invited_by=admin_user,
            email="new@example.com",
            role="developer",
        )
        response = admin_client.delete(f"/api/invitations/{invitation.pk}/")
        assert response.status_code == 204
        invitation.refresh_from_db()
        assert invitation.revoked_at is not None


@pytest.mark.django_db
class TestInvitationPublicDetail:
    def test_valid_token_returns_details(self, api_client, organization, admin_user):
        _invitation, token = create_invitation(
            organization=organization,
            invited_by=admin_user,
            email="new@example.com",
            role="developer",
        )
        response = api_client.get(f"/api/invitations/{token}/")
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "new@example.com"
        assert body["organization_name"] == organization.name

    def test_unknown_token_returns_404(self, api_client):
        response = api_client.get("/api/invitations/not-a-real-token/")
        assert response.status_code == 404

    def test_expired_invitation_returns_404(self, api_client, organization, admin_user):
        invitation, token = create_invitation(
            organization=organization,
            invited_by=admin_user,
            email="new@example.com",
            role="developer",
        )
        invitation.expires_at = timezone.now() - timedelta(seconds=1)
        invitation.save(update_fields=["expires_at"])

        response = api_client.get(f"/api/invitations/{token}/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestInvitationAccept:
    def test_accept_creates_user_membership_and_logs_in(
        self, api_client, organization, admin_user, password
    ):
        _invitation, token = create_invitation(
            organization=organization,
            invited_by=admin_user,
            email="new@example.com",
            role="developer",
        )
        response = api_client.post(f"/api/invitations/{token}/accept/", {"password": password})
        assert response.status_code == 204
        assert "_auth_user_id" in api_client.session

        membership = OrganizationMembership.objects.get(user__email="new@example.com")
        assert membership.organization_id == organization.id
        assert membership.role == CommunityRole.DEVELOPER

    def test_accept_rejects_unknown_token(self, api_client, password):
        response = api_client.post(
            "/api/invitations/not-a-real-token/accept/", {"password": password}
        )
        assert response.status_code == 404

    def test_accept_rejects_already_accepted_invitation(
        self, api_client, organization, admin_user, password
    ):
        _invitation, token = create_invitation(
            organization=organization,
            invited_by=admin_user,
            email="new@example.com",
            role="developer",
        )
        first = api_client.post(f"/api/invitations/{token}/accept/", {"password": password})
        assert first.status_code == 204

        second_client = APIClient()
        second = second_client.post(f"/api/invitations/{token}/accept/", {"password": "different!"})
        assert second.status_code == 404

    def test_accept_rejects_revoked_invitation(
        self, api_client, organization, admin_user, password
    ):
        invitation, token = create_invitation(
            organization=organization,
            invited_by=admin_user,
            email="new@example.com",
            role="developer",
        )
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])

        response = api_client.post(f"/api/invitations/{token}/accept/", {"password": password})
        assert response.status_code == 404

    def test_accept_rejects_missing_csrf_token(self, organization, admin_user, password):
        _invitation, token = create_invitation(
            organization=organization,
            invited_by=admin_user,
            email="new@example.com",
            role="developer",
        )
        client = APIClient(enforce_csrf_checks=True)
        client.get("/api/auth/session/")

        response = client.post(f"/api/invitations/{token}/accept/", {"password": password})
        assert response.status_code == 403
        assert not OrganizationMembership.objects.filter(user__email="new@example.com").exists()


@pytest.mark.django_db
class TestInvitationTenantIsolation:
    def test_admin_cannot_see_or_cancel_another_organizations_invitations(
        self, admin_client, make_user, make_membership
    ):
        other_org = Organization.objects.create(name="Other Co", slug="other-co")
        other_admin_user = make_user("other-admin@example.com")
        make_membership(other_org, other_admin_user, role=CommunityRole.ADMINISTRATOR)
        other_invitation, _token = create_invitation(
            organization=other_org,
            invited_by=other_admin_user,
            email="target@example.com",
            role="developer",
        )

        list_response = admin_client.get("/api/invitations/")
        returned_ids = {i["id"] for i in list_response.json()["results"]}
        assert str(other_invitation.pk) not in returned_ids

        delete_response = admin_client.delete(f"/api/invitations/{other_invitation.pk}/")
        assert delete_response.status_code == 404
        other_invitation.refresh_from_db()
        assert other_invitation.revoked_at is None
