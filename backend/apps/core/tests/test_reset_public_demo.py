import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.services import DEMO_ORGANIZATION_SLUG, DEMO_ROLE_TO_EMAIL
from apps.bugs.models import Bug
from apps.bugs.services import create_bug
from apps.comments.services import create_comment
from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
from apps.projects.models import Project
from apps.projects.services import create_project

User = get_user_model()

RESET_COMMAND = "reset_public_demo"


def run_reset(**extra_options):
    call_command(RESET_COMMAND, confirm_demo_reset=True, **extra_options)


@pytest.fixture
def enable_reset(settings):
    settings.QUORFIX_DEMO_MODE = True
    settings.QUORFIX_DEMO_RESET_ENABLED = True


@pytest.fixture
def seeded_demo(db):
    call_command("seed_demo")
    return Organization.objects.get(slug=DEMO_ORGANIZATION_SLUG)


def _persona_membership(organization, role):
    email = DEMO_ROLE_TO_EMAIL[role]
    return OrganizationMembership.objects.select_related("user").get(
        organization=organization, user__email=email
    )


@pytest.mark.django_db
class TestGuards:
    """Section 30: mandatory refusal tests."""

    def test_refuses_without_confirm_flag(self, settings, seeded_demo):
        settings.QUORFIX_DEMO_MODE = True
        settings.QUORFIX_DEMO_RESET_ENABLED = True
        with pytest.raises(CommandError, match="confirm-demo-reset"):
            call_command(RESET_COMMAND)

    def test_refuses_when_demo_mode_disabled(self, settings, seeded_demo):
        settings.QUORFIX_DEMO_MODE = False
        settings.QUORFIX_DEMO_RESET_ENABLED = True
        with pytest.raises(CommandError, match="QUORFIX_DEMO_MODE"):
            run_reset()

    def test_refuses_when_reset_not_enabled(self, settings, seeded_demo):
        settings.QUORFIX_DEMO_MODE = True
        settings.QUORFIX_DEMO_RESET_ENABLED = False
        with pytest.raises(CommandError, match="QUORFIX_DEMO_RESET_ENABLED"):
            run_reset()

    def test_refuses_when_no_demo_organization_exists(self, db, enable_reset):
        # No seed_demo call — the demo org genuinely does not exist yet.
        with pytest.raises(CommandError, match=DEMO_ORGANIZATION_SLUG):
            run_reset()

    def test_no_data_is_touched_when_guards_refuse(self, settings, seeded_demo):
        settings.QUORFIX_DEMO_MODE = False
        bug_count_before = Bug.objects.filter(organization=seeded_demo).count()
        with pytest.raises(CommandError):
            run_reset()
        assert Bug.objects.filter(organization=seeded_demo).count() == bug_count_before


@pytest.mark.django_db
class TestPreservation:
    """Section 11/30: reset must never touch non-demo/operator data."""

    def test_non_demo_user_survives(self, enable_reset, seeded_demo, make_user):
        bystander = make_user("bystander@example.com")
        run_reset()
        bystander.refresh_from_db()
        assert bystander.is_active

    def test_staff_user_survives(self, enable_reset, seeded_demo, make_user):
        staff = make_user("staffer@example.com")
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        run_reset()
        staff.refresh_from_db()
        assert staff.is_staff is True

    def test_superuser_survives(self, enable_reset, seeded_demo, make_user):
        superuser = make_user("root@example.com")
        superuser.is_superuser = True
        superuser.save(update_fields=["is_superuser"])
        run_reset()
        superuser.refresh_from_db()
        assert superuser.is_superuser is True

    def test_non_demo_organization_survives(self, enable_reset, seeded_demo, organization):
        run_reset()
        assert Organization.objects.filter(pk=organization.pk).exists()

    def test_non_demo_organization_content_survives(
        self, enable_reset, seeded_demo, organization, admin_user, admin_membership
    ):
        project = create_project(
            organization=organization, name="Acme Project", key="ACM", lead=admin_user
        )
        bug = create_bug(
            organization=organization,
            project=project,
            reporter=admin_user,
            membership=admin_membership,
            title="A real customer's bug",
        )
        run_reset()
        assert Project.objects.filter(pk=project.pk).exists()
        assert Bug.objects.filter(pk=bug.pk).exists()

    def test_staff_account_inside_the_demo_organization_is_not_deleted(
        self, enable_reset, seeded_demo, make_user, make_membership
    ):
        # An extra (non-canonical) member who happens to be staff — must be
        # skipped, never deleted, even though it isn't one of the five
        # personas and would otherwise be removed as residue.
        rogue_staff = make_user("rogue-staff@example.com")
        rogue_staff.is_staff = True
        rogue_staff.save(update_fields=["is_staff"])
        make_membership(seeded_demo, rogue_staff, role=CommunityRole.VIEWER)

        run_reset()

        assert User.objects.filter(pk=rogue_staff.pk).exists()
        rogue_staff.refresh_from_db()
        assert rogue_staff.is_staff is True


@pytest.mark.django_db
class TestPersonaRestoration:
    def test_tampered_role_is_repaired(self, enable_reset, seeded_demo):
        membership = _persona_membership(seeded_demo, CommunityRole.DEVELOPER)
        membership.role = CommunityRole.VIEWER
        membership.save(update_fields=["role"])

        run_reset()

        membership.refresh_from_db()
        assert membership.role == CommunityRole.DEVELOPER

    def test_tampered_staff_flag_on_a_persona_is_repaired(self, enable_reset, seeded_demo):
        membership = _persona_membership(seeded_demo, CommunityRole.ADMINISTRATOR)
        user = membership.user
        user.is_staff = True
        user.save(update_fields=["is_staff"])

        run_reset()

        user.refresh_from_db()
        assert user.is_staff is False

    def test_tampered_superuser_flag_on_a_persona_is_repaired(self, enable_reset, seeded_demo):
        membership = _persona_membership(seeded_demo, CommunityRole.QA)
        user = membership.user
        user.is_superuser = True
        user.save(update_fields=["is_superuser"])

        run_reset()

        user.refresh_from_db()
        assert user.is_superuser is False

    def test_deactivated_persona_is_reactivated(self, enable_reset, seeded_demo):
        membership = _persona_membership(seeded_demo, CommunityRole.REPORTER)
        user = membership.user
        user.is_active = False
        user.save(update_fields=["is_active"])

        run_reset()

        user.refresh_from_db()
        assert user.is_active is True

    def test_all_five_personas_are_canonical_after_reset(self, enable_reset, seeded_demo):
        run_reset()
        for role, email in DEMO_ROLE_TO_EMAIL.items():
            membership = OrganizationMembership.objects.select_related("user").get(
                organization=seeded_demo, user__email=email
            )
            assert membership.role == role
            assert membership.user.is_active is True
            assert membership.user.is_staff is False
            assert membership.user.is_superuser is False


@pytest.mark.django_db
class TestVisitorDataRemoval:
    def test_extra_project_is_removed(self, enable_reset, seeded_demo):
        admin = _persona_membership(seeded_demo, CommunityRole.ADMINISTRATOR)
        extra = create_project(
            organization=seeded_demo, name="Visitor Project", key="VIS", lead=admin.user
        )
        run_reset()
        assert not Project.objects.filter(pk=extra.pk).exists()

    def test_extra_bug_and_its_comments_are_removed(self, enable_reset, seeded_demo):
        admin = _persona_membership(seeded_demo, CommunityRole.ADMINISTRATOR)
        project = Project.objects.filter(organization=seeded_demo).first()
        bug = create_bug(
            organization=seeded_demo,
            project=project,
            reporter=admin.user,
            membership=admin,
            title="Visitor-reported bug — should not survive a reset",
        )
        comment = create_comment(bug=bug, author=admin.user, membership=admin, body="hi")
        run_reset()
        assert not Bug.objects.filter(pk=bug.pk).exists()
        from apps.comments.models import Comment

        assert not Comment.objects.filter(pk=comment.pk).exists()

    def test_extra_membership_is_removed(
        self, enable_reset, seeded_demo, make_user, make_membership
    ):
        visitor = make_user("uninvited@example.com")
        membership = make_membership(seeded_demo, visitor, role=CommunityRole.VIEWER)
        run_reset()
        assert not OrganizationMembership.objects.filter(pk=membership.pk).exists()
        assert not User.objects.filter(pk=visitor.pk).exists()

    def test_canonical_seed_content_exists_after_reset(self, enable_reset, seeded_demo):
        run_reset()
        assert Project.objects.filter(organization=seeded_demo).count() >= 1
        assert Bug.objects.filter(organization=seeded_demo).count() >= 1
        assert OrganizationMembership.objects.filter(organization=seeded_demo).count() == len(
            DEMO_ROLE_TO_EMAIL
        )


@pytest.mark.django_db
class TestIdempotency:
    def test_reset_twice_gives_equivalent_canonical_state(self, enable_reset, seeded_demo):
        run_reset()
        first_bug_count = Bug.objects.filter(organization=seeded_demo).count()
        first_project_count = Project.objects.filter(organization=seeded_demo).count()
        first_roles = {
            m.user.email: m.role
            for m in OrganizationMembership.objects.filter(organization=seeded_demo).select_related(
                "user"
            )
        }

        run_reset()

        second_bug_count = Bug.objects.filter(organization=seeded_demo).count()
        second_project_count = Project.objects.filter(organization=seeded_demo).count()
        second_roles = {
            m.user.email: m.role
            for m in OrganizationMembership.objects.filter(organization=seeded_demo).select_related(
                "user"
            )
        }

        assert first_bug_count == second_bug_count
        assert first_project_count == second_project_count
        assert first_roles == second_roles

    def test_reset_after_visitor_activity_converges_to_the_same_state_as_a_clean_reset(
        self, enable_reset, seeded_demo
    ):
        admin = _persona_membership(seeded_demo, CommunityRole.ADMINISTRATOR)
        baseline_bug_count = Bug.objects.filter(organization=seeded_demo).count()
        baseline_project_count = Project.objects.filter(organization=seeded_demo).count()

        create_project(organization=seeded_demo, name="Junk", key="JNK", lead=admin.user)
        create_bug(
            organization=seeded_demo,
            project=Project.objects.filter(organization=seeded_demo).first(),
            reporter=admin.user,
            membership=admin,
            title="Junk bug",
        )

        run_reset()

        assert Bug.objects.filter(organization=seeded_demo).count() == baseline_bug_count
        assert Project.objects.filter(organization=seeded_demo).count() == baseline_project_count


@pytest.mark.django_db
class TestFailureHandling:
    def test_failed_seed_step_rolls_back_the_whole_reset(
        self, enable_reset, seeded_demo, monkeypatch
    ):
        """Failure injection (Section 29): if the reseed phase raises, the
        already-applied deletions must roll back too — a partial reset must
        never be left committed."""
        bug_count_before = Bug.objects.filter(organization=seeded_demo).count()
        project_count_before = Project.objects.filter(organization=seeded_demo).count()

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated seed_demo failure")

        monkeypatch.setattr("apps.core.management.commands.reset_public_demo.call_command", _boom)

        with pytest.raises(RuntimeError):
            run_reset()

        assert Bug.objects.filter(organization=seeded_demo).count() == bug_count_before
        assert Project.objects.filter(organization=seeded_demo).count() == project_count_before
        # The five personas are untouched too — nothing was left half-done.
        assert OrganizationMembership.objects.filter(organization=seeded_demo).count() == len(
            DEMO_ROLE_TO_EMAIL
        )


@pytest.mark.django_db(transaction=True)
class TestConcurrentReset:
    def test_a_reset_refuses_while_another_is_genuinely_in_progress(self, settings):
        # transaction=True + real threads with their own DB connections —
        # session-scoped advisory locks are reentrant *within one session*
        # (the same connection can re-acquire its own held lock), so this
        # can only be demonstrated with a genuinely separate connection,
        # the same pattern apps.organizations.tests.test_concurrency uses.
        import threading

        from django.db import close_old_connections

        from apps.core.pg_advisory_lock import DEMO_RESET_LOCK_KEY, advisory_lock
        from apps.organizations.models import SetupLock

        settings.QUORFIX_DEMO_MODE = True
        settings.QUORFIX_DEMO_RESET_ENABLED = True
        # SetupLock is a migration-seeded singleton row, not re-created
        # automatically after a transaction=True test's table flush — the
        # same gotcha frontend/e2e/global-setup.ts and
        # docs/ACCESS_AND_TESTING.md already document for this exact
        # reason. seed_demo (via setup_instance) requires it to exist.
        SetupLock.objects.get_or_create(id=1)
        call_command("seed_demo")

        outcomes = []
        holding = threading.Event()
        release = threading.Event()

        def hold_lock():
            with advisory_lock(DEMO_RESET_LOCK_KEY):
                holding.set()
                release.wait(timeout=5)
            close_old_connections()

        def attempt_reset():
            holding.wait(timeout=5)
            try:
                run_reset()
                outcomes.append("ok")
            except CommandError as exc:
                outcomes.append("blocked" if "already in progress" in str(exc) else f"error:{exc}")
            finally:
                release.set()
                close_old_connections()

        t1 = threading.Thread(target=hold_lock)
        t2 = threading.Thread(target=attempt_reset)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert outcomes == ["blocked"]
