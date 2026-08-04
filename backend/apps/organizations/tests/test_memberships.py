import pytest

from apps.organizations.models import CommunityRole, Organization, OrganizationMembership


@pytest.mark.django_db
class TestMembershipList:
    def test_requires_authentication(self, api_client):
        response = api_client.get("/api/members/")
        assert response.status_code == 403

    def test_any_member_can_list(
        self, api_client, organization, make_user, make_membership, admin_membership
    ):
        viewer = make_user("viewer@example.com")
        make_membership(organization, viewer, role=CommunityRole.VIEWER)
        api_client.force_login(viewer)

        response = api_client.get("/api/members/")
        assert response.status_code == 200
        assert len(response.json()["results"]) == 2


@pytest.mark.django_db
class TestMembershipMutations:
    def test_non_admin_cannot_change_role(
        self, api_client, organization, make_user, make_membership, admin_membership
    ):
        developer = make_user("dev@example.com")
        dev_membership = make_membership(organization, developer, role=CommunityRole.DEVELOPER)
        api_client.force_login(developer)

        response = api_client.patch(f"/api/members/{dev_membership.pk}/", {"role": "qa"})
        assert response.status_code == 403

    def test_admin_can_change_role(
        self, admin_client, organization, make_user, make_membership
    ):
        developer = make_user("dev@example.com")
        dev_membership = make_membership(organization, developer, role=CommunityRole.DEVELOPER)

        response = admin_client.patch(f"/api/members/{dev_membership.pk}/", {"role": "qa"})
        assert response.status_code == 200
        dev_membership.refresh_from_db()
        assert dev_membership.role == CommunityRole.QA

    def test_admin_can_remove_a_non_admin_member(
        self, admin_client, organization, make_user, make_membership
    ):
        developer = make_user("dev@example.com")
        dev_membership = make_membership(organization, developer, role=CommunityRole.DEVELOPER)

        response = admin_client.delete(f"/api/members/{dev_membership.pk}/")
        assert response.status_code == 204
        assert not OrganizationMembership.objects.filter(pk=dev_membership.pk).exists()

    def test_cannot_demote_the_sole_administrator(self, admin_client, admin_membership):
        response = admin_client.patch(f"/api/members/{admin_membership.pk}/", {"role": "developer"})
        assert response.status_code == 409
        admin_membership.refresh_from_db()
        assert admin_membership.role == CommunityRole.ADMINISTRATOR

    def test_cannot_remove_the_sole_administrator(self, admin_client, admin_membership):
        response = admin_client.delete(f"/api/members/{admin_membership.pk}/")
        assert response.status_code == 409
        assert OrganizationMembership.objects.filter(pk=admin_membership.pk).exists()

    def test_can_demote_an_administrator_when_another_remains(
        self, admin_client, organization, admin_membership, make_user, make_membership
    ):
        second_admin_user = make_user("second-admin@example.com")
        second_admin = make_membership(
            organization, second_admin_user, role=CommunityRole.ADMINISTRATOR
        )

        response = admin_client.patch(f"/api/members/{second_admin.pk}/", {"role": "developer"})
        assert response.status_code == 200


@pytest.mark.django_db
class TestMembershipTenantIsolation:
    def test_admin_cannot_see_or_modify_another_organizations_members(
        self, admin_client, make_user, make_membership
    ):
        other_org = Organization.objects.create(name="Other Co", slug="other-co")
        other_user = make_user("other-admin@example.com")
        other_membership = make_membership(other_org, other_user, role=CommunityRole.ADMINISTRATOR)

        list_response = admin_client.get("/api/members/")
        returned_ids = {m["id"] for m in list_response.json()["results"]}
        assert str(other_membership.pk) not in returned_ids

        patch_response = admin_client.patch(
            f"/api/members/{other_membership.pk}/", {"role": "viewer"}
        )
        assert patch_response.status_code == 404

        delete_response = admin_client.delete(f"/api/members/{other_membership.pk}/")
        assert delete_response.status_code == 404

        other_membership.refresh_from_db()
        assert other_membership.role == CommunityRole.ADMINISTRATOR
