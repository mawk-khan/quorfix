import pytest

from apps.bugs.models import BugStatus, RelationshipType
from apps.bugs.services import (
    BugArchived,
    BugPermissionDenied,
    BugVersionConflict,
    DuplicateBugRelationship,
    DuplicateChainUnverifiable,
    DuplicateCycleDetected,
    DuplicateTargetArchived,
    DuplicateTargetRequired,
    IneligibleAssignee,
    InvalidRelationshipType,
    InvalidTagName,
    ProjectArchivedForBugMutation,
    RelatedBugNotFound,
    SelfRelationshipNotAllowed,
    add_tag,
    archive_bug,
    assign_bug,
    create_relationship,
    remove_relationship,
    remove_tag,
    restore_bug,
    transition_bug,
    unwatch_bug,
    update_bug,
    watch_bug,
)


@pytest.mark.django_db
class TestUpdateBug:
    def test_staff_can_edit_content_and_priority_severity(self, bug, admin_user, admin_membership):
        updated = update_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            expected_version=bug.version,
            title="New title",
            priority="high",
            severity="critical",
            due_date=None,
        )
        assert updated.title == "New title"
        assert updated.priority == "high"
        assert updated.severity == "critical"
        assert updated.version == bug.version + 1

    def test_version_conflict_returns_current_bug(self, bug, admin_user, admin_membership):
        with pytest.raises(BugVersionConflict) as exc_info:
            update_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                expected_version=bug.version + 999,
                title="x",
            )
        assert exc_info.value.bug.pk == bug.pk

    def test_no_op_update_does_not_bump_version(self, bug, admin_user, admin_membership):
        updated = update_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            expected_version=bug.version,
            title=bug.title,
        )
        assert updated.version == bug.version

    def test_reporter_cannot_edit_priority_or_severity(
        self, organization, project, reporter_user, reporter_membership, make_bug
    ):
        own_bug = make_bug(organization, project, reporter_user, membership=reporter_membership)
        with pytest.raises(BugPermissionDenied):
            update_bug(
                bug=own_bug,
                actor=reporter_user,
                membership=reporter_membership,
                expected_version=own_bug.version,
                priority="urgent",
            )

    def test_reporter_can_edit_own_bug_while_new(
        self, organization, project, reporter_user, reporter_membership, make_bug
    ):
        own_bug = make_bug(organization, project, reporter_user, membership=reporter_membership)
        updated = update_bug(
            bug=own_bug,
            actor=reporter_user,
            membership=reporter_membership,
            expected_version=own_bug.version,
            title="Reporter's edit",
        )
        assert updated.title == "Reporter's edit"

    def test_reporter_cannot_edit_another_reporters_bug(
        self,
        organization,
        project,
        reporter_user,
        reporter_membership,
        make_bug,
        make_user,
        make_membership,
    ):
        from apps.organizations.models import CommunityRole

        other_reporter = make_user("other-reporter@example.com")
        make_membership(organization, other_reporter, role=CommunityRole.REPORTER)
        other_bug = make_bug(organization, project, other_reporter)

        with pytest.raises(BugPermissionDenied):
            update_bug(
                bug=other_bug,
                actor=reporter_user,
                membership=reporter_membership,
                expected_version=other_bug.version,
                title="Hijacked",
            )

    def test_reporter_cannot_edit_own_bug_once_work_starts(
        self,
        organization,
        project,
        reporter_user,
        reporter_membership,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        make_bug,
    ):
        own_bug = make_bug(organization, project, reporter_user, membership=reporter_membership)
        in_progress = transition_bug(
            bug=own_bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.ASSIGNED,
            expected_version=own_bug.version,
            assignee_id=str(developer_user.pk),
        )
        with pytest.raises(BugPermissionDenied):
            update_bug(
                bug=in_progress,
                actor=reporter_user,
                membership=reporter_membership,
                expected_version=in_progress.version,
                title="Too late",
            )

    def test_viewer_cannot_edit(self, bug, viewer_user, viewer_membership):
        with pytest.raises(BugPermissionDenied):
            update_bug(
                bug=bug,
                actor=viewer_user,
                membership=viewer_membership,
                expected_version=bug.version,
                title="Nope",
            )


@pytest.mark.django_db
class TestReporterReopen:
    def test_reporter_can_reopen_own_resolved_bug(
        self,
        organization,
        project,
        reporter_user,
        reporter_membership,
        admin_user,
        admin_membership,
        developer_user,
        developer_membership,
        make_bug,
    ):
        own_bug = make_bug(organization, project, reporter_user, membership=reporter_membership)
        assigned = transition_bug(
            bug=own_bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.ASSIGNED,
            expected_version=own_bug.version,
            assignee_id=str(developer_user.pk),
        )
        resolved = transition_bug(
            bug=assigned,
            actor=developer_user,
            membership=developer_membership,
            new_status=BugStatus.IN_PROGRESS,
            expected_version=assigned.version,
        )
        resolved = transition_bug(
            bug=resolved,
            actor=developer_user,
            membership=developer_membership,
            new_status=BugStatus.RESOLVED,
            expected_version=resolved.version,
        )
        assert resolved.resolved_at is not None

        reopened = transition_bug(
            bug=resolved,
            actor=reporter_user,
            membership=reporter_membership,
            new_status=BugStatus.REOPENED,
            expected_version=resolved.version,
        )
        assert reopened.status == BugStatus.REOPENED
        assert reopened.resolved_at is None

    def test_reporter_cannot_perform_other_transitions(
        self, organization, project, reporter_user, reporter_membership, make_bug
    ):
        own_bug = make_bug(organization, project, reporter_user, membership=reporter_membership)
        with pytest.raises(BugPermissionDenied):
            transition_bug(
                bug=own_bug,
                actor=reporter_user,
                membership=reporter_membership,
                new_status=BugStatus.TRIAGED,
                expected_version=own_bug.version,
            )

    def test_reporter_cannot_assign(
        self, bug, reporter_user, reporter_membership, developer_user, developer_membership
    ):
        with pytest.raises(BugPermissionDenied):
            assign_bug(
                bug=bug,
                actor=reporter_user,
                membership=reporter_membership,
                assignee_id=str(developer_user.pk),
                expected_version=bug.version,
            )


@pytest.mark.django_db
class TestAssignment:
    def test_ineligible_role_rejected(
        self, bug, admin_user, admin_membership, viewer_user, viewer_membership
    ):
        with pytest.raises(IneligibleAssignee):
            assign_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                assignee_id=str(viewer_user.pk),
                expected_version=bug.version,
            )

    def test_reporter_role_ineligible_as_assignee(
        self, bug, admin_user, admin_membership, reporter_user, reporter_membership
    ):
        with pytest.raises(IneligibleAssignee):
            assign_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                assignee_id=str(reporter_user.pk),
                expected_version=bug.version,
            )

    def test_unassign(
        self, bug, admin_user, admin_membership, developer_user, developer_membership
    ):
        assigned = assign_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            assignee_id=str(developer_user.pk),
            expected_version=bug.version,
        )
        unassigned = assign_bug(
            bug=assigned,
            actor=admin_user,
            membership=admin_membership,
            assignee_id=None,
            expected_version=assigned.version,
        )
        assert unassigned.assignee is None


@pytest.mark.django_db
class TestArchiveRules:
    def test_archive_then_double_archive_conflicts(self, bug, admin_user, admin_membership):
        from apps.bugs.services import BugAlreadyArchived

        archived = archive_bug(
            bug=bug, actor=admin_user, membership=admin_membership, expected_version=bug.version
        )
        with pytest.raises(BugAlreadyArchived):
            archive_bug(
                bug=archived,
                actor=admin_user,
                membership=admin_membership,
                expected_version=archived.version,
            )

    def test_restore_non_archived_conflicts(self, bug, admin_user, admin_membership):
        from apps.bugs.services import BugNotArchived

        with pytest.raises(BugNotArchived):
            restore_bug(
                bug=bug, actor=admin_user, membership=admin_membership, expected_version=bug.version
            )

    def test_non_admin_cannot_archive(self, bug, developer_user, developer_membership):
        with pytest.raises(BugPermissionDenied):
            archive_bug(
                bug=bug,
                actor=developer_user,
                membership=developer_membership,
                expected_version=bug.version,
            )

    def test_archived_bug_blocks_update(self, bug, admin_user, admin_membership):
        archived = archive_bug(
            bug=bug, actor=admin_user, membership=admin_membership, expected_version=bug.version
        )
        with pytest.raises(BugArchived):
            update_bug(
                bug=archived,
                actor=admin_user,
                membership=admin_membership,
                expected_version=archived.version,
                title="nope",
            )

    def test_archived_project_blocks_mutation_of_existing_bug(
        self, organization, project, bug, admin_user, admin_membership
    ):
        from apps.projects.services import archive_project

        archive_project(project=project)
        with pytest.raises(ProjectArchivedForBugMutation):
            update_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                expected_version=bug.version,
                title="nope",
            )

    def test_archived_project_blocks_archiving_its_bugs_too(
        self, organization, project, bug, admin_user, admin_membership
    ):
        from apps.projects.services import archive_project

        archive_project(project=project)
        with pytest.raises(ProjectArchivedForBugMutation):
            archive_bug(
                bug=bug, actor=admin_user, membership=admin_membership, expected_version=bug.version
            )


@pytest.mark.django_db
class TestTags:
    def test_add_and_remove(self, bug, admin_user, admin_membership):
        tagged = add_tag(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            name="  Backend  ",
            expected_version=bug.version,
        )
        assert [t.name for t in tagged.tags.all()] == ["Backend"]
        assert tagged.version == bug.version + 1

        untagged = remove_tag(
            bug=tagged,
            actor=admin_user,
            membership=admin_membership,
            tag_id=tagged.tags.first().pk,
            expected_version=tagged.version,
        )
        assert untagged.tags.count() == 0
        assert untagged.version == tagged.version + 1

    def test_case_insensitive_reuse(
        self, bug, admin_user, admin_membership, make_bug, project, organization
    ):
        add_tag(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            name="Backend",
            expected_version=bug.version,
        )
        other = make_bug(organization, project, admin_user, membership=admin_membership)
        tagged_other = add_tag(
            bug=other,
            actor=admin_user,
            membership=admin_membership,
            name="backend",
            expected_version=other.version,
        )
        assert tagged_other.tags.first().name == "Backend"  # first casing wins

    def test_adding_same_tag_twice_is_a_no_op(self, bug, admin_user, admin_membership):
        first = add_tag(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            name="dup",
            expected_version=bug.version,
        )
        second = add_tag(
            bug=first,
            actor=admin_user,
            membership=admin_membership,
            name="dup",
            expected_version=first.version,
        )
        assert second.version == first.version
        assert second.tags.count() == 1

    def test_removing_absent_tag_is_a_no_op(self, bug, admin_user, admin_membership):
        result = remove_tag(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            tag_id="00000000-0000-0000-0000-000000000000",
            expected_version=bug.version,
        )
        assert result.version == bug.version

    def test_blank_name_rejected(self, bug, admin_user, admin_membership):
        with pytest.raises(InvalidTagName):
            add_tag(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                name="   ",
                expected_version=bug.version,
            )

    def test_too_long_name_rejected(self, bug, admin_user, admin_membership):
        with pytest.raises(InvalidTagName):
            add_tag(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                name="x" * 51,
                expected_version=bug.version,
            )


@pytest.mark.django_db
class TestWatching:
    def test_watch_and_unwatch_are_idempotent_and_dont_touch_version(
        self, bug, viewer_user, viewer_membership
    ):
        version_before = bug.version
        watch_bug(bug=bug, user=viewer_user)
        watch_bug(bug=bug, user=viewer_user)  # idempotent
        bug.refresh_from_db()
        assert bug.version == version_before
        assert bug.watchers.filter(pk=viewer_user.pk).exists()

        unwatch_bug(bug=bug, user=viewer_user)
        unwatch_bug(bug=bug, user=viewer_user)  # idempotent
        bug.refresh_from_db()
        assert bug.version == version_before
        assert not bug.watchers.filter(pk=viewer_user.pk).exists()

    def test_no_activity_written_for_watch(self, bug, viewer_user, viewer_membership):
        from apps.activities.models import BugActivity

        count_before = BugActivity.objects.filter(bug=bug).count()
        watch_bug(bug=bug, user=viewer_user)
        assert BugActivity.objects.filter(bug=bug).count() == count_before


@pytest.mark.django_db
class TestRelationships:
    def test_blocks_created(
        self, bug, make_bug, project, organization, admin_user, admin_membership
    ):
        other = make_bug(organization, project, admin_user, membership=admin_membership)
        updated = create_relationship(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            related_bug_id=str(other.pk),
            relationship_type=RelationshipType.BLOCKS,
            expected_version=bug.version,
        )
        assert updated.version == bug.version + 1

    def test_exact_duplicate_blocks_rejected(
        self, bug, make_bug, project, organization, admin_user, admin_membership
    ):
        other = make_bug(organization, project, admin_user, membership=admin_membership)
        updated = create_relationship(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            related_bug_id=str(other.pk),
            relationship_type=RelationshipType.BLOCKS,
            expected_version=bug.version,
        )
        with pytest.raises(DuplicateBugRelationship):
            create_relationship(
                bug=updated,
                actor=admin_user,
                membership=admin_membership,
                related_bug_id=str(other.pk),
                relationship_type=RelationshipType.BLOCKS,
                expected_version=updated.version,
            )

    def test_relates_to_is_symmetric_deduplicated(
        self, bug, make_bug, project, organization, admin_user, admin_membership
    ):
        other = make_bug(organization, project, admin_user, membership=admin_membership)
        updated = create_relationship(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            related_bug_id=str(other.pk),
            relationship_type=RelationshipType.RELATES_TO,
            expected_version=bug.version,
        )
        # Now try creating the reverse direction from the other bug — must
        # be rejected as the same canonical relationship, not stored twice.
        other.refresh_from_db()
        with pytest.raises(DuplicateBugRelationship):
            create_relationship(
                bug=other,
                actor=admin_user,
                membership=admin_membership,
                related_bug_id=str(updated.pk),
                relationship_type=RelationshipType.RELATES_TO,
                expected_version=other.version,
            )

    def test_self_relationship_rejected(self, bug, admin_user, admin_membership):
        with pytest.raises(SelfRelationshipNotAllowed):
            create_relationship(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                related_bug_id=str(bug.pk),
                relationship_type=RelationshipType.RELATES_TO,
                expected_version=bug.version,
            )

    def test_cross_organization_target_not_found(self, bug, admin_user, admin_membership):
        from apps.bugs.models import Bug
        from apps.organizations.models import Organization
        from apps.projects.models import Project, ProjectStatus

        other_org = Organization.objects.create(name="Other Co", slug="other-co-rel")
        other_project = Project.objects.create(
            organization=other_org, key="OTH", name="Other", status=ProjectStatus.ACTIVE
        )
        other_bug = Bug.objects.create(
            organization=other_org,
            project=other_project,
            number=1,
            key="OTH-1",
            title="Cross-org",
            reporter=admin_user,
        )
        with pytest.raises(RelatedBugNotFound):
            create_relationship(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                related_bug_id=str(other_bug.pk),
                relationship_type=RelationshipType.RELATES_TO,
                expected_version=bug.version,
            )

    def test_duplicate_of_cannot_be_created_via_relationships_endpoint(
        self, bug, make_bug, project, organization, admin_user, admin_membership
    ):
        other = make_bug(organization, project, admin_user, membership=admin_membership)
        with pytest.raises(InvalidRelationshipType):
            create_relationship(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                related_bug_id=str(other.pk),
                relationship_type=RelationshipType.DUPLICATE_OF,
                expected_version=bug.version,
            )

    def test_remove_relationship(
        self, bug, make_bug, project, organization, admin_user, admin_membership
    ):
        other = make_bug(organization, project, admin_user, membership=admin_membership)
        updated = create_relationship(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            related_bug_id=str(other.pk),
            relationship_type=RelationshipType.BLOCKS,
            expected_version=bug.version,
        )
        from apps.bugs.models import BugRelationship

        relationship = BugRelationship.objects.get(from_bug=updated, to_bug=other)
        removed = remove_relationship(
            bug=updated,
            actor=admin_user,
            membership=admin_membership,
            relationship_id=relationship.pk,
            expected_version=updated.version,
        )
        assert not BugRelationship.objects.filter(pk=relationship.pk).exists()
        assert removed.version == updated.version + 1


@pytest.mark.django_db
class TestDuplicateTransition:
    def test_requires_target(self, bug, admin_user, admin_membership):
        with pytest.raises(DuplicateTargetRequired):
            transition_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                new_status=BugStatus.DUPLICATE,
                expected_version=bug.version,
            )

    def test_marks_duplicate_atomically(
        self, bug, make_bug, project, organization, admin_user, admin_membership
    ):
        original = make_bug(organization, project, admin_user, membership=admin_membership)
        updated = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.DUPLICATE,
            expected_version=bug.version,
            duplicate_of=str(original.pk),
        )
        assert updated.status == BugStatus.DUPLICATE
        assert updated.resolved_at is not None
        assert updated.version == bug.version + 1

        from apps.bugs.models import BugRelationship

        assert BugRelationship.objects.filter(
            from_bug=updated, to_bug=original, relationship_type=RelationshipType.DUPLICATE_OF
        ).exists()

    def test_self_duplicate_rejected(self, bug, admin_user, admin_membership):
        with pytest.raises(SelfRelationshipNotAllowed):
            transition_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                new_status=BugStatus.DUPLICATE,
                expected_version=bug.version,
                duplicate_of=str(bug.pk),
            )

    def test_archived_target_rejected(
        self, bug, make_bug, project, organization, admin_user, admin_membership
    ):
        original = make_bug(organization, project, admin_user, membership=admin_membership)
        original = archive_bug(
            bug=original,
            actor=admin_user,
            membership=admin_membership,
            expected_version=original.version,
        )
        with pytest.raises(DuplicateTargetArchived):
            transition_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                new_status=BugStatus.DUPLICATE,
                expected_version=bug.version,
                duplicate_of=str(original.pk),
            )

    def test_two_bug_cycle_rejected(
        self, bug, make_bug, project, organization, admin_user, admin_membership
    ):
        other = make_bug(organization, project, admin_user, membership=admin_membership)
        # bug -> duplicate_of -> other
        bug = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.DUPLICATE,
            expected_version=bug.version,
            duplicate_of=str(other.pk),
        )
        # other -> duplicate_of -> bug would close a 2-cycle
        with pytest.raises(DuplicateCycleDetected):
            transition_bug(
                bug=other,
                actor=admin_user,
                membership=admin_membership,
                new_status=BugStatus.DUPLICATE,
                expected_version=other.version,
                duplicate_of=str(bug.pk),
            )

    def test_chain_too_deep_to_verify_is_rejected_not_accepted(
        self, organization, project, admin_user, admin_membership, make_bug
    ):
        from apps.bugs import services as bugs_services

        # Build a duplicate_of chain longer than MAX_DUPLICATE_CHAIN_DEPTH so
        # traversal can neither confirm nor rule out a cycle in time — this
        # must be rejected, never silently treated as safe.
        chain = [
            make_bug(organization, project, admin_user, membership=admin_membership)
            for _ in range(bugs_services.MAX_DUPLICATE_CHAIN_DEPTH + 5)
        ]
        for i in range(len(chain) - 1):
            current = transition_bug(
                bug=chain[i],
                actor=admin_user,
                membership=admin_membership,
                new_status=BugStatus.DUPLICATE,
                expected_version=chain[i].version,
                duplicate_of=str(chain[i + 1].pk),
            )
            chain[i] = current

        new_bug = make_bug(organization, project, admin_user, membership=admin_membership)
        with pytest.raises(DuplicateChainUnverifiable):
            transition_bug(
                bug=new_bug,
                actor=admin_user,
                membership=admin_membership,
                new_status=BugStatus.DUPLICATE,
                expected_version=new_bug.version,
                duplicate_of=str(chain[0].pk),
            )
