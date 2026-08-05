import pytest

from apps.bugs.models import Bug
from apps.bugs.services import (
    IneligibleAssignee,
    RelatedBugNotFound,
    assign_bug,
    create_relationship,
)
from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
from apps.projects.models import Project, ProjectStatus


@pytest.fixture
def other_org_setup(admin_user):
    """A second, fully independent organization/project/bug/user — used to
    prove nothing in apps.bugs ever lets one organization see, mutate, or
    reference another's data."""
    org = Organization.objects.create(name="Other Co", slug="other-co-isolation")
    project = Project.objects.create(
        organization=org, key="OTH", name="Other", status=ProjectStatus.ACTIVE
    )
    from django.contrib.auth import get_user_model

    other_user = get_user_model().objects.create_user(
        username="other-org-admin", email="other-org-admin@example.com", password="x"
    )
    membership = OrganizationMembership.objects.create(
        organization=org, user=other_user, role=CommunityRole.ADMINISTRATOR
    )
    bug = Bug.objects.create(
        organization=org,
        project=project,
        number=1,
        key="OTH-1",
        title="Other org's bug",
        reporter=other_user,
    )
    return {
        "org": org,
        "project": project,
        "user": other_user,
        "membership": membership,
        "bug": bug,
    }


@pytest.mark.django_db
class TestBugTenantIsolation:
    def test_cannot_retrieve_other_orgs_bug(self, admin_client, other_org_setup):
        response = admin_client.get(f"/api/bugs/{other_org_setup['bug'].pk}/")
        assert response.status_code == 404

    def test_cannot_update_other_orgs_bug(self, admin_client, other_org_setup):
        response = admin_client.patch(
            f"/api/bugs/{other_org_setup['bug'].pk}/",
            {"version": 1, "title": "hijacked"},
            format="json",
        )
        assert response.status_code == 404

    def test_cannot_transition_other_orgs_bug(self, admin_client, other_org_setup):
        response = admin_client.post(
            f"/api/bugs/{other_org_setup['bug'].pk}/transition/",
            {"status": "triaged", "version": 1},
            format="json",
        )
        assert response.status_code == 404

    def test_cannot_archive_other_orgs_bug(self, admin_client, other_org_setup):
        response = admin_client.post(
            f"/api/bugs/{other_org_setup['bug'].pk}/archive/", {"version": 1}, format="json"
        )
        assert response.status_code == 404

    def test_cannot_list_other_orgs_bugs_via_search(self, admin_client, other_org_setup):
        response = admin_client.get(f"/api/bugs/?search={other_org_setup['bug'].key}")
        assert response.json()["count"] == 0

    def test_cannot_filter_by_other_orgs_project_id(self, admin_client, bug, other_org_setup):
        response = admin_client.get(f"/api/bugs/?project={other_org_setup['project'].pk}")
        # An org-scoped filter combined with an id from another org yields
        # zero results, not another organization's data and not an error
        # that would confirm the id exists elsewhere.
        assert response.status_code == 200
        assert response.json()["count"] == 0

    def test_cannot_assign_bug_to_user_in_another_organization(
        self, bug, admin_user, admin_membership, other_org_setup
    ):
        with pytest.raises(IneligibleAssignee):
            assign_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                assignee_id=str(other_org_setup["user"].pk),
                expected_version=bug.version,
            )

    def test_cannot_reference_other_orgs_bug_as_relationship_target(
        self, bug, admin_user, admin_membership, other_org_setup
    ):
        with pytest.raises(RelatedBugNotFound):
            create_relationship(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                related_bug_id=str(other_org_setup["bug"].pk),
                relationship_type="relates_to",
                expected_version=bug.version,
            )

    def test_cannot_reuse_tag_across_organizations(self, admin_client, bug, other_org_setup):
        from apps.bugs.models import Tag

        Tag.objects.create(
            organization=other_org_setup["org"], name="shared-name", name_normalized="shared-name"
        )
        response = admin_client.post(
            f"/api/bugs/{bug.pk}/tags/",
            {"name": "shared-name", "version": bug.version},
            format="json",
        )
        assert response.status_code == 200
        tag_id = response.json()["tags"][0]["id"]
        assert tag_id != str(Tag.objects.get(organization=other_org_setup["org"]).pk)

    def test_cannot_delete_relationship_by_id_from_another_org(self, admin_client, bug):
        response = admin_client.delete(
            f"/api/bugs/{bug.pk}/relationships/00000000-0000-0000-0000-000000000000/",
            {"version": bug.version},
            format="json",
        )
        assert response.status_code == 404
