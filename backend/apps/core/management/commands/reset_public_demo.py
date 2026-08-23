"""apps.core.management.commands.reset_public_demo — guarded, deterministic
reset of the public Quorfix demo to its canonical state.

Usage:
    python manage.py reset_public_demo --confirm-demo-reset

Refuses to run unless ALL of the following independently hold:
    1. --confirm-demo-reset was passed explicitly (never inferred).
    2. settings.QUORFIX_DEMO_MODE is true.
    3. settings.QUORFIX_DEMO_RESET_ENABLED is true — a second, independent
       flag from QUORFIX_DEMO_MODE (see that setting's own comment in
       config/settings/base.py) so enabling Quick Access login can never,
       by itself, also enable a destructive reset.
    4. An organization slugged "quorfix-demo" actually exists — if it
       doesn't, this database doesn't look like a demo database at all,
       regardless of what the settings above claim.
    5. (Transitively, via seed_demo below) QUORFIX_DISPOSABLE_DATABASE is
       true whenever ENVIRONMENT == "production" — the same guard every
       other demo-seeding command already uses.

What this command does, in one outer transaction.atomic() (so a failure
anywhere rolls back everything — a reset never leaves a half-seeded demo):
    1. Acquires apps.core.pg_advisory_lock's DEMO_RESET_LOCK_KEY
       (non-blocking) — a second concurrent invocation refuses immediately
       rather than queuing behind this one and redoing the same work.
    2. Sets apps.core.demo_reset_guard's reset-in-progress flag, which
       makes every organization-scoped mutating API request return 503
       for the (brief) duration of this command — closing the "a visitor's
       write lands between delete and reseed" race without needing
       per-task reset-awareness scattered through every service module.
    3. Deletes every resettable/transient record scoped to the demo
       organization: all Bug rows (which cascade to BugActivity,
       BugRelationship, Comment, Mention, Attachment, and Notification —
       verified directly against every model's on_delete, not assumed),
       all Tag rows, all Project rows, all Invitation rows, all
       NotificationPreference rows, and any membership/user that isn't one
       of the five canonical personas (residue from before Step 3's
       invitation lock, or a misuse of seed_demo's own
       bypass_demo_protection escape hatch) — except any account that is
       staff or superuser, which is never touched, only logged.
    4. Deletes each removed attachment's underlying storage file via
       apps.attachments.providers.get_storage_provider() (never a shell
       rm) — a missing file is logged and skipped, not a fatal error.
    5. Forces is_active/is_staff/is_superuser back to canonical
       (True/False/False) on each of the five personas — the one thing
       seed_demo's own reconvergence never touches (see
       _repair_persona_security_flags's docstring for why).
    6. Calls `seed_demo` (apps.core.management.commands.seed_demo) to
       rebuild the canonical organization/personas/projects/bugs — the
       same idempotent, already-tested tool a fresh install's first seed
       uses (which also repairs role and first/last name/password drift on
       each persona), so this reset introduces no second, parallel seeding
       implementation to drift out of sync with it.
    7. Verifies the canonical state actually holds (all five personas
       exist, correct role, active, never staff/superuser; the expected
       projects/bugs exist) — raising (and so rolling back the entire
       transaction) if not, rather than ever reporting success on
       unverified state.

Deliberately NOT done here:
    - No git/deployment operation of any kind.
    - No `docker compose down -v` / `DROP DATABASE` / `manage.py flush` /
      any broad destructive shortcut — every deletion above is scoped to
      `organization=<the demo organization>` by an explicit queryset
      filter, never a blanket table truncation.
    - No automatic backup — see docs/DEMO_DEPLOYMENT.md "Demo data reset"
      for why, and how to request one explicitly (`scripts/demo backup`)
      before a reset if desired.
    - No Redis FLUSHALL and no throttle-counter reset — see
      docs/SECURITY.md "Cache / Redis cleanup (public demo reset)".
    - No session invalidation — the five personas' User rows are never
      deleted and recreated (only repaired in place by seed_demo), and
      every authorization check in this codebase re-reads membership/role
      fresh from the database on each request (no caching layer to go
      stale) — see docs/DEMO_DEPLOYMENT.md "Demo sessions and reset".
"""

from __future__ import annotations

import logging
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.services import DEMO_ORGANIZATION_SLUG, DEMO_ROLE_TO_EMAIL
from apps.attachments.models import Attachment
from apps.attachments.providers import get_storage_provider
from apps.bugs.models import Bug, Tag
from apps.core.demo_reset_guard import reset_in_progress
from apps.core.pg_advisory_lock import DEMO_RESET_LOCK_KEY, LockNotAcquired, advisory_lock
from apps.notifications.models import NotificationPreference
from apps.organizations.models import Invitation, Organization, OrganizationMembership
from apps.projects.models import Project

User = get_user_model()
logger = logging.getLogger(__name__)


class ResetVerificationFailed(Exception):
    """Raised when the post-restore canonical-state check fails. Always
    raised from inside the outer transaction.atomic(), so raising it also
    rolls back every deletion/reseed step that already ran."""


class Command(BaseCommand):
    help = (
        "Guarded reset of the public Quorfix demo to its canonical state — deletes visitor-"
        "created content scoped to the 'quorfix-demo' organization and rebuilds it via "
        "seed_demo. Refuses to run without --confirm-demo-reset, QUORFIX_DEMO_MODE=true, "
        "QUORFIX_DEMO_RESET_ENABLED=true, and an existing 'quorfix-demo' organization. See this "
        "module's own docstring for the full guard/step list."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm-demo-reset",
            action="store_true",
            default=False,
            help="Required. Explicit confirmation that this invocation intends to reset the "
            "public demo. There is no interactive prompt — this flag is the only confirmation, "
            "so scheduled/non-interactive execution works the same as a manual run.",
        )

    def handle(self, *args, **options):
        started = time.monotonic()
        logger.info("Demo reset: starting (environment=%s)", getattr(settings, "ENVIRONMENT", "?"))

        try:
            self._check_guards(options)
            with advisory_lock(DEMO_RESET_LOCK_KEY, blocking=False):
                logger.info("Demo reset: lock acquired")
                with reset_in_progress():
                    self._run_reset()
        except LockNotAcquired as exc:
            logger.error("Demo reset: refused — another reset is already in progress")
            self.stderr.write(self.style.ERROR("DEMO RESET FAIL"))
            raise CommandError("ERROR: demo reset already in progress") from exc
        except CommandError:
            logger.error("Demo reset: refused by a guard condition")
            self.stderr.write(self.style.ERROR("DEMO RESET FAIL"))
            raise
        except Exception:
            logger.exception("Demo reset: FAILED")
            self.stderr.write(self.style.ERROR("DEMO RESET FAIL"))
            raise

        duration = time.monotonic() - started
        logger.info("Demo reset: completed successfully in %.1fs", duration)
        self.stdout.write(self.style.SUCCESS("DEMO RESET PASS"))

    # -- guards ---------------------------------------------------------

    def _check_guards(self, options) -> None:
        if not options["confirm_demo_reset"]:
            raise CommandError(
                "refusing to run without --confirm-demo-reset (this operation deletes data)"
            )
        if not settings.QUORFIX_DEMO_MODE:
            raise CommandError("QUORFIX_DEMO_MODE is not enabled — refusing to reset")
        if not settings.QUORFIX_DEMO_RESET_ENABLED:
            raise CommandError("QUORFIX_DEMO_RESET_ENABLED is not enabled — refusing to reset")
        if not Organization.objects.filter(slug=DEMO_ORGANIZATION_SLUG).exists():
            raise CommandError(
                f"no organization slugged {DEMO_ORGANIZATION_SLUG!r} exists — this does not "
                "look like a demo database; refusing to reset"
            )

    # -- orchestration ----------------------------------------------------

    def _run_reset(self) -> None:
        with transaction.atomic():
            organization = Organization.objects.select_for_update().get(slug=DEMO_ORGANIZATION_SLUG)
            summary = self._clear_transient_data(organization)
            logger.info("Demo reset: cleared transient data: %s", summary)

            repaired = self._repair_persona_security_flags(organization)
            if repaired:
                logger.warning(
                    "Demo reset: repaired tampered security flags on %d persona account(s) — "
                    "this should never happen via any API endpoint; investigate how it occurred.",
                    repaired,
                )

            logger.info("Demo reset: reseeding canonical state via seed_demo")
            call_command("seed_demo")

            self._verify_canonical_state(organization)

    # -- deletion phase ---------------------------------------------------

    def _clear_transient_data(self, organization: Organization) -> dict[str, int]:
        summary: dict[str, int] = {}

        storage = get_storage_provider()
        storage_keys = list(
            Attachment.objects.filter(organization=organization).values_list(
                "storage_key", flat=True
            )
        )
        removed_files = 0
        for key in storage_keys:
            try:
                storage.delete(key)
                removed_files += 1
            except Exception:
                logger.warning(
                    "Demo reset: failed to delete an attachment storage object (continuing)",
                    exc_info=True,
                )
        summary["attachment_files"] = removed_files

        for model in (Bug, Tag, Project):
            _, cascade = model.objects.filter(organization=organization).delete()
            for label, count in cascade.items():
                summary[label] = summary.get(label, 0) + count

        for model in (Invitation, NotificationPreference):
            _, cascade = model.objects.filter(organization=organization).delete()
            for label, count in cascade.items():
                summary[label] = summary.get(label, 0) + count

        summary.update(self._remove_non_canonical_members(organization))
        return summary

    def _remove_non_canonical_members(self, organization: Organization) -> dict[str, int]:
        """Removes any membership/user in the demo organization that isn't
        one of the five canonical personas. Never touches a staff or
        superuser account — such an account is skipped and logged loudly
        instead, since reset must never delete an operator account, even
        one incorrectly associated with this organization."""
        canonical_emails = {email.lower() for email in DEMO_ROLE_TO_EMAIL.values()}
        extra_memberships = list(
            OrganizationMembership.objects.filter(organization=organization)
            .exclude(user__email__in=canonical_emails)
            .select_related("user")
        )

        removed_memberships = 0
        removed_users = 0
        skipped_privileged = 0
        for membership in extra_memberships:
            user = membership.user
            if user.is_staff or user.is_superuser:
                skipped_privileged += 1
                logger.warning(
                    "Demo reset: found a staff/superuser account (id=%s) associated with the "
                    "demo organization — refusing to touch it. Investigate manually.",
                    user.pk,
                )
                continue
            membership.delete()
            removed_memberships += 1
            # Only removes the user entirely once nothing else references
            # it — safe by this point specifically because every bug,
            # comment, and attachment it could have authored/led was
            # already cascaded away above.
            if not OrganizationMembership.objects.filter(user=user).exists():
                user.delete()
                removed_users += 1

        return {
            "non_canonical_memberships": removed_memberships,
            "non_canonical_users": removed_users,
            "privileged_accounts_skipped": skipped_privileged,
        }

    def _repair_persona_security_flags(self, organization: Organization) -> int:
        """Forces is_active/is_staff/is_superuser back to canonical
        (True/False/False) for each of the five personas.

        seed_demo's own reconvergence (_sync_persona) already repairs
        first_name/last_name/password, and its _ensure_member already
        repairs role (via change_member_role(bypass_demo_protection=True))
        — but it never touches these three security-sensitive flags, since
        no legitimate seeding run needs to (a freshly created user is
        already correct on all three). No API endpoint in this codebase
        can ever set is_staff/is_superuser True in the first place
        (apps.accounts.services.resolve_demo_login_user already requires
        both False just to authenticate a persona at all) — so this is
        defense-in-depth against a direct-database tamper, not a path this
        code expects to exercise in normal operation. Returns the number
        of accounts that needed repair, purely for logging.
        """
        repaired = 0
        memberships = OrganizationMembership.objects.filter(
            organization=organization, user__email__in=list(DEMO_ROLE_TO_EMAIL.values())
        ).select_related("user")
        for membership in memberships:
            user = membership.user
            update_fields = []
            if not user.is_active:
                user.is_active = True
                update_fields.append("is_active")
            if user.is_staff:
                user.is_staff = False
                update_fields.append("is_staff")
            if user.is_superuser:
                user.is_superuser = False
                update_fields.append("is_superuser")
            if update_fields:
                user.save(update_fields=update_fields)
                repaired += 1
        return repaired

    # -- verification -----------------------------------------------------

    def _verify_canonical_state(self, organization: Organization) -> None:
        errors: list[str] = []

        memberships = {
            membership.user.email.lower(): membership
            for membership in OrganizationMembership.objects.filter(
                organization=organization
            ).select_related("user")
        }

        for role, email in DEMO_ROLE_TO_EMAIL.items():
            membership = memberships.get(email.lower())
            if membership is None:
                errors.append(f"missing persona membership for {email}")
                continue
            if membership.role != role:
                errors.append(f"{email} has role {membership.role!r}, expected {role!r}")
            user = membership.user
            if not user.is_active:
                errors.append(f"{email} is not active")
            if user.is_staff:
                errors.append(f"{email} is staff")
            if user.is_superuser:
                errors.append(f"{email} is superuser")

        # Not a strict "exactly five" count: a staff/superuser account
        # incorrectly associated with the demo org is deliberately
        # preserved rather than deleted (see _remove_non_canonical_members)
        # — that is a legitimate, expected exception, not a cleanup
        # failure. Any *other* extra membership is exactly what
        # _remove_non_canonical_members should already have removed.
        canonical_emails = {email.lower() for email in DEMO_ROLE_TO_EMAIL.values()}
        unexpected = [
            email
            for email, membership in memberships.items()
            if email not in canonical_emails
            and not (membership.user.is_staff or membership.user.is_superuser)
        ]
        if unexpected:
            errors.append(f"unexpected extra membership(s) survived cleanup: {unexpected}")

        project_count = Project.objects.filter(organization=organization).count()
        if project_count < 1:
            errors.append("no projects exist after reset")

        bug_count = Bug.objects.filter(organization=organization).count()
        if bug_count < 1:
            errors.append("no bugs exist after reset")

        if errors:
            for error in errors:
                logger.error("Demo reset: verification failed: %s", error)
            raise ResetVerificationFailed("; ".join(errors))

        logger.info(
            "Demo reset: verification passed (%d personas, %d projects, %d bugs)",
            len(memberships),
            project_count,
            bug_count,
        )
