import pytest
from django.db import IntegrityError, transaction

from apps.bugs.models import Bug, BugRelationship, RelationshipType, Tag


@pytest.mark.django_db
class TestBugConstraints:
    def test_unique_number_per_project(self, organization, project, admin_user):
        Bug.objects.create(
            organization=organization,
            project=project,
            number=1,
            key=f"{project.key}-1",
            title="First",
            reporter=admin_user,
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Bug.objects.create(
                    organization=organization,
                    project=project,
                    number=1,
                    key=f"{project.key}-1b",
                    title="Duplicate number",
                    reporter=admin_user,
                )

    def test_unique_key_per_org(self, organization, project, admin_user):
        Bug.objects.create(
            organization=organization,
            project=project,
            number=1,
            key="DUPKEY-1",
            title="First",
            reporter=admin_user,
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Bug.objects.create(
                    organization=organization,
                    project=project,
                    number=2,
                    key="DUPKEY-1",
                    title="Second",
                    reporter=admin_user,
                )

    def test_defaults(self, organization, project, admin_user):
        b = Bug.objects.create(
            organization=organization,
            project=project,
            number=1,
            key=f"{project.key}-1",
            title="Defaults",
            reporter=admin_user,
        )
        assert b.status == "new"
        assert b.priority == "medium"
        assert b.severity == "major"
        assert b.version == 1
        assert b.archived_at is None


@pytest.mark.django_db
class TestTagConstraints:
    def test_case_insensitive_unique_name(self, organization):
        Tag.objects.create(organization=organization, name="Backend", name_normalized="backend")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Tag.objects.create(
                    organization=organization, name="backend", name_normalized="backend"
                )


@pytest.mark.django_db
class TestBugRelationshipConstraints:
    def test_no_self_reference(self, bug):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                BugRelationship.objects.create(
                    organization=bug.organization,
                    from_bug=bug,
                    to_bug=bug,
                    relationship_type=RelationshipType.RELATES_TO,
                )

    def test_no_exact_duplicate(self, bug, make_bug, project, admin_user):
        other = make_bug(bug.organization, project, admin_user)
        BugRelationship.objects.create(
            organization=bug.organization,
            from_bug=bug,
            to_bug=other,
            relationship_type=RelationshipType.BLOCKS,
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                BugRelationship.objects.create(
                    organization=bug.organization,
                    from_bug=bug,
                    to_bug=other,
                    relationship_type=RelationshipType.BLOCKS,
                )
