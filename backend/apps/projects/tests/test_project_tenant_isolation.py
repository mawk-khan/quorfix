import pytest
from django.utils import timezone

from apps.organizations.models import CommunityRole, Organization


@pytest.mark.django_db
class TestProjectTenantIsolation:
    def test_list_does_not_include_other_organizations_projects(
        self, admin_client, organization, make_project
    ):
        other_org = Organization.objects.create(name="Other Co", slug="other-co")
        make_project(other_org, key="ENG", name="Other Engine")

        response = admin_client.get("/api/projects/")
        assert response.json()["count"] == 0

    def test_retrieve_another_organizations_project_is_404(self, admin_client, make_project):
        other_org = Organization.objects.create(name="Other Co", slug="other-co")
        other_project = make_project(other_org, key="ENG")

        response = admin_client.get(f"/api/projects/{other_project.pk}/")
        assert response.status_code == 404

    def test_update_another_organizations_project_is_404(self, admin_client, make_project):
        other_org = Organization.objects.create(name="Other Co", slug="other-co")
        other_project = make_project(other_org, key="ENG")

        response = admin_client.patch(f"/api/projects/{other_project.pk}/", {"name": "Hijacked"})
        assert response.status_code == 404
        other_project.refresh_from_db()
        assert other_project.name != "Hijacked"

    def test_archive_another_organizations_project_is_404(self, admin_client, make_project):
        other_org = Organization.objects.create(name="Other Co", slug="other-co")
        other_project = make_project(other_org, key="ENG")

        response = admin_client.post(f"/api/projects/{other_project.pk}/archive/")
        assert response.status_code == 404
        other_project.refresh_from_db()
        assert other_project.archived_at is None

    def test_restore_another_organizations_project_is_404(self, admin_client, make_project):
        other_org = Organization.objects.create(name="Other Co", slug="other-co")
        other_project = make_project(other_org, key="ENG")
        other_project.archived_at = timezone.now()
        other_project.save(update_fields=["archived_at"])

        response = admin_client.post(f"/api/projects/{other_project.pk}/restore/")
        assert response.status_code == 404
        other_project.refresh_from_db()
        assert other_project.archived_at is not None

    def test_same_key_in_different_organizations_does_not_collide(
        self, admin_client, organization, make_project
    ):
        other_org = Organization.objects.create(name="Other Co", slug="other-co")
        make_project(other_org, key="ENG", name="Other Engine")

        response = admin_client.post("/api/projects/", {"name": "Our Engine", "key": "ENG"})
        assert response.status_code == 201

    def test_lead_must_belong_to_the_target_organization_not_any_organization(
        self, admin_client, organization, make_user, make_membership
    ):
        other_org = Organization.objects.create(name="Other Co", slug="other-co")
        other_org_user = make_user("member-of-other-org@example.com")
        make_membership(other_org, other_org_user, role=CommunityRole.DEVELOPER)

        response = admin_client.post(
            "/api/projects/", {"name": "Engine", "key": "ENG", "lead": str(other_org_user.pk)}
        )
        assert response.status_code == 400
        assert "lead" in response.json()
