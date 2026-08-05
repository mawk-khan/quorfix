import pytest

from apps.bugs import workflow
from apps.bugs.models import BugStatus
from apps.bugs.services import (
    AssigneeRequiredForTransition,
    InvalidWorkflowTransition,
    transition_bug,
)
from apps.core.registries import workflow_registry


@pytest.mark.django_db
class TestCommunityTransitionMatrix:
    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            (BugStatus.NEW, BugStatus.TRIAGED),
            (BugStatus.TRIAGED, BugStatus.DEFERRED),
            (BugStatus.IN_PROGRESS, BugStatus.READY_FOR_QA),
            (BugStatus.READY_FOR_QA, BugStatus.RESOLVED),
            (BugStatus.RESOLVED, BugStatus.CLOSED),
            (BugStatus.RESOLVED, BugStatus.REOPENED),
            (BugStatus.CLOSED, BugStatus.REOPENED),
            (BugStatus.BLOCKED, BugStatus.TRIAGED),
            (BugStatus.BLOCKED, BugStatus.IN_PROGRESS),
            (BugStatus.REOPENED, BugStatus.BLOCKED),
            (BugStatus.DUPLICATE, BugStatus.REOPENED),
            (BugStatus.CANNOT_REPRODUCE, BugStatus.REOPENED),
            (BugStatus.WONT_FIX, BugStatus.REOPENED),
        ],
    )
    def test_allowed_edges(self, project, from_status, to_status):
        assert workflow.is_valid_transition(project, from_status, to_status) is True

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            (BugStatus.CLOSED, BugStatus.IN_PROGRESS),
            (BugStatus.CLOSED, BugStatus.RESOLVED),
            (BugStatus.NEW, BugStatus.RESOLVED),
            (BugStatus.NEW, BugStatus.CLOSED),
            (BugStatus.BLOCKED, BugStatus.RESOLVED),
            (BugStatus.DUPLICATE, BugStatus.CLOSED),
            (BugStatus.RESOLVED, BugStatus.NEW),
        ],
    )
    def test_rejected_edges(self, project, from_status, to_status):
        assert workflow.is_valid_transition(project, from_status, to_status) is False

    def test_closed_is_terminal_except_for_reopened(self, project):
        matrix = workflow.get_transition_matrix(project)
        assert matrix[BugStatus.CLOSED] == frozenset({BugStatus.REOPENED})

    def test_registry_empty_falls_back_to_community_matrix(self, project):
        assert workflow_registry.is_registered(workflow.WORKFLOW_PROVIDER_KEY) is False
        assert workflow.get_transition_matrix(project) is workflow.COMMUNITY_TRANSITIONS


@pytest.mark.django_db
class TestTimestampSideEffects:
    @pytest.mark.parametrize(
        "to_status",
        [BugStatus.RESOLVED, BugStatus.DUPLICATE, BugStatus.CANNOT_REPRODUCE, BugStatus.WONT_FIX],
    )
    def test_resolution_statuses_set_resolved_at(self, bug, to_status):
        class Fake:
            resolved_at = None
            closed_at = None

        fake = Fake()
        workflow.apply_timestamp_side_effects(fake, to_status)
        assert fake.resolved_at is not None
        assert fake.closed_at is None

    def test_closed_preserves_resolved_at_and_sets_closed_at(self):
        class Fake:
            resolved_at = "already-set"
            closed_at = None

        fake = Fake()
        workflow.apply_timestamp_side_effects(fake, BugStatus.CLOSED)
        assert fake.resolved_at == "already-set"
        assert fake.closed_at is not None

    def test_reopened_clears_both(self):
        class Fake:
            resolved_at = "was-set"
            closed_at = "was-set"

        fake = Fake()
        workflow.apply_timestamp_side_effects(fake, BugStatus.REOPENED)
        assert fake.resolved_at is None
        assert fake.closed_at is None


@pytest.mark.django_db
class TestAssigneeRequiredTransitions:
    def test_new_to_assigned_requires_assignee(self, bug, admin_user, admin_membership):
        with pytest.raises(AssigneeRequiredForTransition):
            transition_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                new_status=BugStatus.ASSIGNED,
                expected_version=bug.version,
            )

    def test_new_to_assigned_succeeds_with_assignee_supplied_atomically(
        self, bug, admin_user, admin_membership, developer_user, developer_membership
    ):
        updated = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.ASSIGNED,
            expected_version=bug.version,
            assignee_id=str(developer_user.pk),
        )
        assert updated.status == BugStatus.ASSIGNED
        assert updated.assignee_id == developer_user.pk
        assert updated.version == bug.version + 1

    def test_triaged_to_in_progress_requires_existing_assignee(
        self, bug, admin_user, admin_membership
    ):
        triaged = transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.TRIAGED,
            expected_version=bug.version,
        )
        with pytest.raises(AssigneeRequiredForTransition):
            transition_bug(
                bug=triaged,
                actor=admin_user,
                membership=admin_membership,
                new_status=BugStatus.IN_PROGRESS,
                expected_version=triaged.version,
            )

    def test_assign_alone_never_changes_status(
        self, bug, admin_user, admin_membership, developer_user, developer_membership
    ):
        from apps.bugs.services import assign_bug

        updated = assign_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            assignee_id=str(developer_user.pk),
            expected_version=bug.version,
        )
        assert updated.status == BugStatus.NEW
        assert updated.assignee_id == developer_user.pk


@pytest.mark.django_db
def test_invalid_status_value_is_rejected(bug, admin_user, admin_membership):
    with pytest.raises(InvalidWorkflowTransition):
        transition_bug(
            bug=bug,
            actor=admin_user,
            membership=admin_membership,
            new_status="not_a_real_status",
            expected_version=bug.version,
        )


@pytest.mark.django_db
def test_archived_bug_cannot_be_transitioned_until_restored(bug, admin_user, admin_membership):
    from apps.bugs.services import BugArchived, archive_bug

    archived = archive_bug(
        bug=bug, actor=admin_user, membership=admin_membership, expected_version=bug.version
    )
    with pytest.raises(BugArchived):
        transition_bug(
            bug=archived,
            actor=admin_user,
            membership=admin_membership,
            new_status=BugStatus.TRIAGED,
            expected_version=archived.version,
        )
