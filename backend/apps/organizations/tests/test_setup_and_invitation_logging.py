"""Chunk J §8: setup-completion and invitation-acceptance logging."""

import logging

import pytest


@pytest.mark.django_db
class TestSetupLogging:
    def test_completed_setup_logs_at_info_with_user_and_organization_id(self, api_client, caplog):
        with caplog.at_level(logging.INFO, logger="apps.organizations.views"):
            response = api_client.post(
                "/api/setup/",
                {
                    "organization_name": "Acme",
                    "email": "founder@example.com",
                    "password": "Str0ngPassw0rd!",
                    "first_name": "Founder",
                    "last_name": "Person",
                },
            )
        assert response.status_code == 204
        records = [r for r in caplog.records if r.name == "apps.organizations.views"]
        info_record = next(r for r in records if r.levelno == logging.INFO)
        assert "completed" in info_record.getMessage()
        assert info_record.user_id != "-"
        assert info_record.organization_id != "-"

    def test_rejected_setup_does_not_log_the_password(self, api_client, admin_user, caplog):
        # First setup already exists via the SetupLock seeded state implied
        # by admin_user/admin_membership not being used here — instead this
        # drives the simpler "not allowed" path directly by calling setup a
        # second time; either rejection branch must never log the password.
        fake_password = "sUp3r-Secret-Marker-Pw!"
        with caplog.at_level(logging.DEBUG):
            api_client.post(
                "/api/setup/",
                {
                    "organization_name": "Second Org",
                    "email": "second@example.com",
                    "password": fake_password,
                    "first_name": "A",
                    "last_name": "B",
                },
            )
        for record in caplog.records:
            assert fake_password not in record.getMessage()


@pytest.mark.django_db
class TestInvitationAcceptanceLogging:
    def test_accepted_invitation_logs_at_info_with_user_and_organization_id(
        self, api_client, organization, admin_user, admin_membership, caplog
    ):
        from apps.organizations.services import create_invitation

        _invitation, raw_token = create_invitation(
            organization=organization,
            invited_by=admin_user,
            email="newmember@example.com",
            role="developer",
        )
        with caplog.at_level(logging.INFO, logger="apps.organizations.views"):
            response = api_client.post(
                f"/api/invitations/{raw_token}/accept/",
                {"password": "Str0ngPassw0rd!", "first_name": "New", "last_name": "Member"},
            )
        assert response.status_code == 204
        records = [r for r in caplog.records if r.name == "apps.organizations.views"]
        info_record = next(r for r in records if r.levelno == logging.INFO)
        assert "accepted" in info_record.getMessage()
        assert info_record.user_id != "-"
        assert info_record.organization_id == str(organization.id)
