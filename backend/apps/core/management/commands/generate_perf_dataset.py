"""Generates a disposable, deterministic performance-testing dataset.

SAFETY — read before running anywhere but a local disposable database:

  * Refuses unconditionally under production settings (ENVIRONMENT ==
    "production"), matching seed_demo/seed_e2e_*'s own guard.
  * Refuses unless BUGFIXER_DISPOSABLE_DATABASE=true is set in the
    environment — a variable that exists *only* for this command; a real
    deployment has no reason to ever set it, so its absence is a strong,
    purpose-built signal, not a repurposed one.
  * Refuses if the target database's own configured NAME looks like a
    production database (contains "prod", case-insensitively) — one
    additional, non-sole signal on top of the two above, since a name check
    alone is easy to defeat by accident (this project's own default
    development AND production database name is the same literal string,
    "bugfixer" — see docker-compose.yml / docker-compose.prod.yml — so a
    name-only gate would either always or never fire).
  * Refuses if the seed_demo organization (slug "bug-fixer-demo") or either
    E2E fixture organization (slugs "bug-e2e-org", "analytics-e2e-org")
    exists in the target database — this command must never run against a
    database also used for demo or E2E data; point BUGFIXER_DISPOSABLE_DATABASE
    at a genuinely separate database instead.
  * The --full (100,000-bug) profile additionally requires --full AND
    --confirm-disposable-database together — never inferred from DEBUG,
    from BUGFIXER_DISPOSABLE_DATABASE alone, or from either flag alone.
  * Cleanup (--cleanup-existing-perf-data) requires that same
    --confirm-disposable-database flag, prints exactly what will be
    deleted before deleting it, and is scoped *only* to organizations
    whose slug starts with "perf-" (asserted immediately before every
    delete) — it can structurally never touch demo or E2E organizations,
    and never issues a bare TRUNCATE or sequence reset.

OWNERSHIP MARKER — every row this command creates is identifiable by:
  * organization.slug starting with "perf-"
  * user.email ending in "@perf.invalid"
  * project.key starting with "PERF"
  * a {"perf_dataset": true, "seed": <seed>} entry in each bug's "created"
    BugActivity.metadata (the one model in this generator with a free-form
    JSON field safe to use as a marker)

WHY bulk_create INSTEAD OF THE REAL SERVICE LAYER — apps.bugs.services.
create_bug (and friends) each open a transaction, take a row lock on the
owning Project, and commit individually; that is correct and necessary for
real concurrent user traffic, and hopelessly slow for 100,000 bugs (tens of
minutes to hours, dominated by per-row lock/commit overhead rather than
actual work). This command instead builds rows in memory and writes them
with bulk_create in batches, reconstructing the same invariants the real
services enforce by hand. Every place this happens is documented at the
function that does it:
  * apps.bugs.services.create_bug's sequential (project, number) numbering
    -> _build_bugs_for_project
  * apps.bugs.workflow.apply_timestamp_side_effects' resolved_at/closed_at
    rules -> _resolve_status_timestamps
  * apps.notifications.models.Notification's comment-required-for-
    comment-events CheckConstraint -> _build_notifications
  * apps.attachments.models.Attachment's status/timestamp CheckConstraint
    -> _build_attachments

This command deliberately does NOT attempt to replicate every legal
transition path through apps.bugs.workflow.COMMUNITY_TRANSITIONS for
padding/intermediate activity rows — only the *final* status-changing
activity (and, for reopened bugs, the resolution-then-reopen pair) is
transition-matrix-accurate; additional padding activities use verbs that
carry no graph-position meaning (ASSIGNED, PRIORITY_CHANGED, TAG_ADDED),
matching the identical simplification already made by
apps.core.demo_data.backdate_bug_history ("a cosmetic simplification...
rather than a correctness issue for anything the dashboard computes").

Every random choice is drawn from a single seeded random.Random(seed)
instance (never the global `random` module), so the exact same arguments
always produce the exact same dataset.
"""

from __future__ import annotations

import datetime
import random
import uuid
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.activities.models import ActivityVerb, BugActivity
from apps.attachments.models import Attachment, AttachmentStatus, ScanStatus
from apps.attachments.policies import CAN_UPLOAD_ROLES
from apps.bugs.models import Bug, BugPriority, BugSeverity, BugStatus
from apps.bugs.policies import ASSIGNABLE_ROLES, CREATE_ROLES
from apps.bugs.workflow import OPEN_STATUSES
from apps.comments.models import Comment, CommentStatus, Mention
from apps.comments.policies import CAN_COMMENT_ROLES
from apps.core.env import get_bool
from apps.notifications.models import Notification, NotificationEventType
from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
from apps.projects.models import Project

User = get_user_model()

PERF_SLUG_PREFIX = "perf-"
PERF_EMAIL_DOMAIN = "perf.invalid"
PERF_KEY_PREFIX = "PERF"
PERF_PASSWORD = "PerfDatasetPass123!"  # noqa: S105 - throwaway, disposable-database-only accounts

# Never generated by this command, but must never exist in the same database
# as it either — see the module docstring's "Refuses if ... exists" bullet.
PROTECTED_ORG_SLUGS = frozenset({"bug-fixer-demo", "bug-e2e-org", "analytics-e2e-org"})

DEFAULT_PROFILE = {
    "organizations": 1,
    "projects_per_organization": 5,
    "users_per_organization": 10,
    "bugs_per_organization": 1_000,
    "comments_per_bug": 1.5,
    "activities_per_bug": 3.0,
    "notifications_per_user": 15.0,
    "attachment_rate": 0.1,
}

FULL_PROFILE = {
    "organizations": 5,
    "projects_per_organization": 20,  # 100 projects total
    "users_per_organization": 50,
    "bugs_per_organization": 20_000,  # 100,000 bugs total
    "comments_per_bug": 1.5,
    "activities_per_bug": 3.0,
    "notifications_per_user": 15.0,
    "attachment_rate": 0.1,
}

# Weighted so the generated backlog matches Chunk I's requested shape:
# 65-75% open, 15-25% resolution statuses, a small closed population, with
# a separate reopened-history pass layered on top afterward (see
# _pick_reopened_bug_indices) rather than folded into this table, since
# "reopened" isn't really a resting state so much as a two-step history.
_STATUS_WEIGHTS: list[tuple[str, float]] = [
    (BugStatus.NEW, 12),
    (BugStatus.TRIAGED, 14),
    (BugStatus.ASSIGNED, 14),
    (BugStatus.IN_PROGRESS, 16),
    (BugStatus.READY_FOR_QA, 8),
    (BugStatus.BLOCKED, 6),
    (BugStatus.RESOLVED, 12),
    (BugStatus.DUPLICATE, 4),
    (BugStatus.CANNOT_REPRODUCE, 3),
    (BugStatus.WONT_FIX, 3),
    (BugStatus.DEFERRED, 4),
    (BugStatus.CLOSED, 4),
]
# REOPENED is deliberately excluded — it's never drawn from this table, only
# ever assigned via the separate reopened-history pass in
# _build_bugs_for_project (a resting status vs. a two-step history).
assert {s for s, _ in _STATUS_WEIGHTS} == set(BugStatus.values) - {BugStatus.REOPENED}
assert abs(sum(w for _, w in _STATUS_WEIGHTS) - 100) < 1e-9

_PRIORITY_WEIGHTS: list[tuple[str, float]] = [
    (BugPriority.URGENT, 8),
    (BugPriority.HIGH, 22),
    (BugPriority.MEDIUM, 50),
    (BugPriority.LOW, 20),
]

_SEVERITY_WEIGHTS: list[tuple[str, float]] = [
    (BugSeverity.BLOCKER, 4),
    (BugSeverity.CRITICAL, 9),
    (BugSeverity.MAJOR, 45),
    (BugSeverity.MINOR, 32),
    (BugSeverity.TRIVIAL, 10),
]

_TITLE_SUBJECTS = [
    "Login form",
    "Dashboard chart",
    "Search results",
    "Export button",
    "Notification bell",
    "Comment editor",
    "Attachment upload",
    "Project filter",
    "Bug list",
    "Mention picker",
    "Session handling",
    "Password reset",
    "CSV export",
    "Activity feed",
    "Assignee dropdown",
    "Tag input",
    "Due date picker",
    "Archive action",
    "Watcher toggle",
    "Status transition",
]
_TITLE_PROBLEMS = [
    "fails to render on slow connections",
    "throws an unhandled error",
    "loses state on refresh",
    "is unresponsive on mobile",
    "shows stale data",
    "does not respect the selected filter",
    "times out under load",
    "duplicates entries",
    "ignores the configured timezone",
    "breaks pagination",
    "renders incorrect totals",
    "does not update in real time",
]

_ACTIVITY_PADDING_VERBS = [
    ActivityVerb.ASSIGNED,
    ActivityVerb.PRIORITY_CHANGED,
    ActivityVerb.TAG_ADDED,
]


def _weighted_choice(rng: random.Random, weights: list[tuple[str, float]]) -> str:
    total = sum(w for _, w in weights)
    pick = rng.uniform(0, total)
    upto = 0.0
    for value, weight in weights:
        upto += weight
        if pick <= upto:
            return value
    return weights[-1][0]


def _is_production_settings() -> bool:
    return settings.ENVIRONMENT == "production"


def _database_name_looks_like_production() -> bool:
    name = str(connection.settings_dict.get("NAME") or "")
    return "prod" in name.lower()


@dataclass
class GeneratedOrg:
    organization: Organization
    users: list = field(default_factory=list)  # list[User]
    memberships: list = field(default_factory=list)  # list[OrganizationMembership]
    projects: list = field(default_factory=list)  # list[Project]


class Command(BaseCommand):
    help = (
        "Generates a disposable, deterministic performance-testing dataset "
        "(organizations, users, projects, bugs, comments, activities, "
        "notifications, attachment metadata). Development/test only — see "
        "this module's own docstring for the full safety model. Never run "
        "against a database you are not prepared to lose."
    )

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--organizations", type=int, default=None)
        parser.add_argument("--projects-per-organization", type=int, default=None)
        parser.add_argument("--users-per-organization", type=int, default=None)
        parser.add_argument("--bugs-per-organization", type=int, default=None)
        parser.add_argument("--comments-per-bug", type=float, default=None)
        parser.add_argument("--activities-per-bug", type=float, default=None)
        parser.add_argument("--notifications-per-user", type=float, default=None)
        parser.add_argument("--attachment-rate", type=float, default=None)
        parser.add_argument("--batch-size", type=int, default=2000)
        parser.add_argument(
            "--full",
            action="store_true",
            help="Use the full (~100,000-bug) profile instead of the default small one. "
            "Requires --confirm-disposable-database as well.",
        )
        parser.add_argument(
            "--confirm-disposable-database",
            action="store_true",
            help="Required alongside --full, and alongside --cleanup-existing-perf-data. "
            "Never inferred from DEBUG or from BUGFIXER_DISPOSABLE_DATABASE alone.",
        )
        parser.add_argument(
            "--cleanup-existing-perf-data",
            action="store_true",
            help="Delete every perf-owned organization (and everything scoped under it) "
            "instead of generating new data. Requires --confirm-disposable-database.",
        )

    # -- entry point ---------------------------------------------------------

    def handle(self, *args, **options):
        self._check_safety(options)

        if options["cleanup_existing_perf_data"]:
            self._cleanup()
            return

        profile = self._resolve_profile(options)
        rng = random.Random(options["seed"])
        batch_size = options["batch_size"]
        if batch_size < 1:
            raise CommandError("--batch-size must be at least 1.")

        started = timezone.now()
        self.stdout.write(
            f"Generating performance dataset (seed={options['seed']}, "
            f"organizations={profile['organizations']}, "
            f"projects/org={profile['projects_per_organization']}, "
            f"bugs/org={profile['bugs_per_organization']}) ..."
        )

        totals = {
            "organizations": 0,
            "users": 0,
            "memberships": 0,
            "projects": 0,
            "bugs": 0,
            "activities": 0,
            "comments": 0,
            "mentions": 0,
            "attachments": 0,
            "notifications": 0,
        }
        status_counts: dict[str, int] = {}

        for org_index in range(profile["organizations"]):
            generated = self._generate_organization(
                rng, org_index, profile, batch_size, status_counts
            )
            totals["organizations"] += 1
            totals["users"] += len(generated.users)
            totals["memberships"] += len(generated.memberships)
            totals["projects"] += len(generated.projects)
            for project in generated.projects:
                totals["bugs"] += project._perf_bug_count  # noqa: SLF001 - internal bookkeeping, see _build_bugs_for_project
                totals["activities"] += project._perf_activity_count
                totals["comments"] += project._perf_comment_count
                totals["mentions"] += project._perf_mention_count
                totals["attachments"] += project._perf_attachment_count
                totals["notifications"] += project._perf_notification_count
            self.stdout.write(
                f"  org {org_index + 1}/{profile['organizations']} "
                f"({generated.organization.slug}): "
                f"{sum(p._perf_bug_count for p in generated.projects)} bugs written."
            )

        elapsed = (timezone.now() - started).total_seconds()
        self._report(totals, status_counts, elapsed)

    # -- safety ---------------------------------------------------------------

    def _check_safety(self, options: dict) -> None:
        if _is_production_settings():
            raise CommandError(
                "generate_perf_dataset refuses to run with production settings "
                f"(SETTINGS_MODULE={settings.SETTINGS_MODULE!r}). This command exists for "
                "local performance testing only."
            )

        if not get_bool("BUGFIXER_DISPOSABLE_DATABASE", False):
            raise CommandError(
                "generate_perf_dataset refuses to run without BUGFIXER_DISPOSABLE_DATABASE=true "
                "in the environment. This variable exists only to gate this command — set it "
                "only when pointed at a database you are prepared to lose entirely, never your "
                "real development or production database."
            )

        if _database_name_looks_like_production():
            raise CommandError(
                f"generate_perf_dataset refuses to run: the configured database name "
                f"({connection.settings_dict.get('NAME')!r}) contains 'prod'. This is one of "
                "several independent safety checks (see this module's docstring) — rename the "
                "disposable database, or point POSTGRES_DB at something else, if this is a "
                "false positive."
            )

        protected = sorted(
            Organization.objects.filter(slug__in=PROTECTED_ORG_SLUGS).values_list("slug", flat=True)
        )
        if protected:
            raise CommandError(
                "generate_perf_dataset refuses to run: this database already contains "
                f"protected organization(s) {protected!r} (seed_demo and/or E2E fixture data). "
                "Point BUGFIXER_DISPOSABLE_DATABASE at a genuinely separate, disposable database "
                "instead of one shared with demo or E2E data."
            )

        if options["cleanup_existing_perf_data"] or options["full"]:
            if not options["confirm_disposable_database"]:
                flag = (
                    "--cleanup-existing-perf-data"
                    if options["cleanup_existing_perf_data"]
                    else "--full"
                )
                raise CommandError(
                    f"{flag} also requires --confirm-disposable-database. This is deliberately "
                    "never inferred from DEBUG, from BUGFIXER_DISPOSABLE_DATABASE alone, or from "
                    f"{flag} alone — two independent, explicit flags are required together."
                )

    # -- profile resolution -----------------------------------------------

    def _resolve_profile(self, options: dict) -> dict:
        base = dict(FULL_PROFILE if options["full"] else DEFAULT_PROFILE)
        overrides = {
            "organizations": options["organizations"],
            "projects_per_organization": options["projects_per_organization"],
            "users_per_organization": options["users_per_organization"],
            "bugs_per_organization": options["bugs_per_organization"],
            "comments_per_bug": options["comments_per_bug"],
            "activities_per_bug": options["activities_per_bug"],
            "notifications_per_user": options["notifications_per_user"],
            "attachment_rate": options["attachment_rate"],
        }
        for key, value in overrides.items():
            if value is not None:
                base[key] = value

        if base["organizations"] < 1:
            raise CommandError("--organizations must be at least 1.")
        if base["projects_per_organization"] < 1:
            raise CommandError("--projects-per-organization must be at least 1.")
        if base["users_per_organization"] < 2:
            raise CommandError(
                "--users-per-organization must be at least 2 "
                "(need at least an administrator and one other member)."
            )
        if base["bugs_per_organization"] < 0:
            raise CommandError("--bugs-per-organization cannot be negative.")
        if not 0 <= base["attachment_rate"] <= 1:
            raise CommandError("--attachment-rate must be between 0 and 1.")
        return base

    # -- per-organization generation --------------------------------------

    def _next_org_ordinal(self) -> int:
        existing = Organization.objects.filter(slug__startswith=PERF_SLUG_PREFIX).count()
        return existing

    def _generate_organization(
        self,
        rng: random.Random,
        org_index: int,
        profile: dict,
        batch_size: int,
        status_counts: dict,
    ) -> GeneratedOrg:
        ordinal = self._next_org_ordinal() + 1
        organization = Organization.objects.create(
            name=f"Performance Org {ordinal}",
            slug=f"{PERF_SLUG_PREFIX}{ordinal:03d}",
            is_active=True,
        )

        users = self._build_users(organization, ordinal, profile["users_per_organization"])
        User.objects.bulk_create(users, batch_size=batch_size)

        memberships = self._build_memberships(rng, organization, users)
        OrganizationMembership.objects.bulk_create(memberships, batch_size=batch_size)

        projects = self._build_projects(
            rng, organization, ordinal, profile["projects_per_organization"], users
        )
        Project.objects.bulk_create(projects, batch_size=batch_size)

        staff_users = [
            u for u, m in zip(users, memberships, strict=True) if m.role in ASSIGNABLE_ROLES
        ]
        reporter_eligible = [
            u for u, m in zip(users, memberships, strict=True) if m.role in CREATE_ROLES
        ]
        commenter_eligible = [
            u for u, m in zip(users, memberships, strict=True) if m.role in CAN_COMMENT_ROLES
        ]
        uploader_eligible = [
            u for u, m in zip(users, memberships, strict=True) if m.role in CAN_UPLOAD_ROLES
        ]

        bug_shares = self._uneven_shares(rng, profile["bugs_per_organization"], len(projects))
        # Roughly the top third of projects (by generation order) are
        # archived — "some archived projects" from Chunk I's requested
        # distribution shape.
        archived_project_indices = set(
            rng.sample(range(len(projects)), k=max(1, len(projects) // 6))
            if len(projects) >= 6
            else []
        )

        for project_index, (project, bug_count) in enumerate(
            zip(projects, bug_shares, strict=True)
        ):
            self._build_bugs_for_project(
                rng=rng,
                organization=organization,
                project=project,
                bug_count=bug_count,
                reporters=reporter_eligible or users,
                assignees=staff_users or users,
                commenters=commenter_eligible or users,
                uploaders=uploader_eligible or users,
                profile=profile,
                seed=rng.getrandbits(32),
                batch_size=batch_size,
                status_counts=status_counts,
                archive_project=project_index in archived_project_indices,
            )

        notifications = self._build_notifications(rng, organization, users, projects, profile)
        for start in range(0, len(notifications), batch_size):
            Notification.objects.bulk_create(
                notifications[start : start + batch_size], batch_size=batch_size
            )
        total_notifications = len(notifications)
        # Attributed to the last project purely so the per-org total in
        # handle()'s summary line adds up without a second bookkeeping
        # structure — cosmetic only, never read per-project.
        if projects:
            projects[-1]._perf_notification_count += total_notifications  # noqa: SLF001

        return GeneratedOrg(
            organization=organization, users=users, memberships=memberships, projects=projects
        )

    # -- users / memberships / projects -----------------------------------

    def _build_users(self, organization: Organization, ordinal: int, count: int) -> list:
        # Keyed by the organization's persistent ordinal (unique across
        # every organization this command has ever created, even across
        # multiple invocations without an intervening cleanup) rather than
        # the loop-local index into *this* invocation's --organizations
        # range, which resets to 0 every run — using the loop-local index
        # here would collide with a previous run's still-present users on
        # User's global unique-lower(email) constraint.
        hashed_password = make_password(PERF_PASSWORD)
        users = []
        for i in range(count):
            uid = uuid.uuid4()
            users.append(
                User(
                    id=uid,
                    username=f"perf-org{ordinal}-user{i}-{uid.hex[:8]}",
                    email=f"perf-org{ordinal}-user{i}@{PERF_EMAIL_DOMAIN}",
                    first_name=f"Perf{i}",
                    last_name=f"Org{ordinal}",
                    password=hashed_password,
                    is_active=True,
                )
            )
        return users

    def _build_memberships(
        self, rng: random.Random, organization: Organization, users: list
    ) -> list:
        role_weights = [
            (CommunityRole.DEVELOPER, 30),
            (CommunityRole.QA, 15),
            (CommunityRole.REPORTER, 30),
            (CommunityRole.VIEWER, 20),
        ]
        memberships = []
        now = timezone.now()
        for index, user in enumerate(users):
            # First user in every org is always an administrator — every
            # generated organization needs at least one, and this keeps it
            # deterministic rather than leaving it to chance.
            role = (
                CommunityRole.ADMINISTRATOR if index == 0 else _weighted_choice(rng, role_weights)
            )
            joined_at = now - datetime.timedelta(days=rng.randint(0, 365))
            memberships.append(
                OrganizationMembership(
                    organization=organization, user=user, role=role, joined_at=joined_at
                )
            )
        return memberships

    def _build_projects(
        self, rng: random.Random, organization: Organization, ordinal: int, count: int, users: list
    ) -> list:
        statuses = ["active"] * 7 + ["planning"] * 2 + ["on_hold"] * 1
        projects = []
        for i in range(count):
            project = Project(
                organization=organization,
                name=f"Perf Project {ordinal}-{i}",
                key=f"{PERF_KEY_PREFIX}{ordinal}{i:02d}",
                status=rng.choice(statuses),
                lead=rng.choice(users) if users else None,
                next_bug_number=1,
            )
            # Internal-only bookkeeping counters, not model fields — cleared
            # of any risk of ever being persisted since bulk_create only
            # ever writes declared model fields.
            project._perf_bug_count = 0
            project._perf_activity_count = 0
            project._perf_comment_count = 0
            project._perf_mention_count = 0
            project._perf_attachment_count = 0
            project._perf_notification_count = 0
            projects.append(project)
        return projects

    def _uneven_shares(self, rng: random.Random, total: int, buckets: int) -> list[int]:
        """Splits `total` across `buckets` with deliberately uneven sizes
        (a few large projects, several small ones) rather than an even
        division — "uneven project sizes" from Chunk I's requested shape.
        Uses random positive weights so the split is seed-deterministic."""
        if buckets == 1:
            return [total]
        weights = [rng.uniform(0.2, 1.0) ** 2 for _ in range(buckets)]
        weight_sum = sum(weights)
        shares = [int(total * w / weight_sum) for w in weights]
        # Integer division loses a few bugs to rounding — hand them to the
        # largest bucket so the organization's total exactly matches
        # bugs_per_organization.
        shortfall = total - sum(shares)
        if shortfall:
            largest = max(range(buckets), key=lambda i: shares[i])
            shares[largest] += shortfall
        return shares

    # -- bugs / activities / comments / mentions / attachments ------------

    def _build_bugs_for_project(
        self,
        *,
        rng: random.Random,
        organization: Organization,
        project: Project,
        bug_count: int,
        reporters: list,
        assignees: list,
        commenters: list,
        uploaders: list,
        profile: dict,
        seed: int,
        batch_size: int,
        status_counts: dict,
        archive_project: bool,
    ) -> None:
        """Reconstructs apps.bugs.services.create_bug's numbering invariant
        by hand: bugs get sequential `number` 1..bug_count within this
        project, `key` = f"{project.key}-{number}", and the project's
        next_bug_number is advanced to bug_count + 1 *after* every bug is
        written — so an ordinary create_bug() call against a perf project
        afterward continues the sequence correctly instead of colliding.
        """
        now = timezone.now()
        earliest = now - datetime.timedelta(days=180)

        bugs: list[Bug] = []
        activities: list[BugActivity] = []
        comments: list[Comment] = []
        mentions: list[Mention] = []
        attachments: list[Attachment] = []

        # ~8% of this project's bugs get a resolve-then-reopen history —
        # "5-10% reopened history" from the requested distribution.
        reopened_indices = set(
            rng.sample(range(bug_count), k=max(0, round(bug_count * rng.uniform(0.05, 0.10))))
            if bug_count
            else []
        )

        for number in range(1, bug_count + 1):
            bug_id = uuid.uuid4()
            key = f"{project.key}-{number}"
            created_at = earliest + datetime.timedelta(
                seconds=rng.uniform(0, (now - earliest).total_seconds())
            )
            reporter = rng.choice(reporters)
            # 10-20% unassigned.
            assignee = None if rng.random() < rng.uniform(0.10, 0.20) else rng.choice(assignees)

            is_reopened = (number - 1) in reopened_indices
            status = BugStatus.REOPENED if is_reopened else _weighted_choice(rng, _STATUS_WEIGHTS)
            if status in {BugStatus.ASSIGNED, BugStatus.IN_PROGRESS} and assignee is None:
                assignee = rng.choice(assignees)

            priority = _weighted_choice(rng, _PRIORITY_WEIGHTS)
            severity = _weighted_choice(rng, _SEVERITY_WEIGHTS)

            # 5-10% overdue: a past due_date on a bug that is still open.
            due_date = None
            if status in OPEN_STATUSES and rng.random() < rng.uniform(0.05, 0.10):
                due_date = (now - datetime.timedelta(days=rng.randint(1, 30))).date()
            elif rng.random() < 0.35:
                due_date = (created_at + datetime.timedelta(days=rng.randint(3, 60))).date()

            resolved_at, closed_at, resolution_activity_at, reopen_activity_at = (
                _resolve_status_timestamps(rng, status=status, created_at=created_at, now=now)
            )

            # Some archived bugs even in non-archived projects, plus every
            # bug in an archived project — "some archived bugs" / "some
            # archived projects" from the requested distribution.
            archived_at = None
            if archive_project or rng.random() < 0.03:
                archived_at = created_at + datetime.timedelta(days=rng.randint(1, 90))
                if archived_at > now:
                    archived_at = now

            title = f"{rng.choice(_TITLE_SUBJECTS)} {rng.choice(_TITLE_PROBLEMS)}"

            bug = Bug(
                id=bug_id,
                organization=organization,
                project=project,
                number=number,
                key=key,
                title=title,
                description=f"Auto-generated performance fixture bug #{number} for {project.key}.",
                category=rng.choice(["Frontend", "Backend", "API", "Performance", "Data", ""]),
                status=status,
                priority=priority,
                severity=severity,
                reporter=reporter,
                assignee=assignee,
                due_date=due_date,
                resolved_at=resolved_at,
                closed_at=closed_at,
                archived_at=archived_at,
                version=1,
                created_at=created_at,
                updated_at=created_at,
            )
            bugs.append(bug)
            status_counts[status] = status_counts.get(status, 0) + 1

            activities.extend(
                _build_activities_for_bug(
                    rng,
                    organization,
                    bug,
                    status,
                    created_at,
                    resolution_activity_at,
                    reopen_activity_at,
                    seed,
                    target_count=profile["activities_per_bug"],
                )
            )

            bug_comments = _build_comments_for_bug(
                rng,
                organization,
                bug,
                commenters,
                created_at,
                now,
                target_average=profile["comments_per_bug"],
            )
            comments.extend(bug_comments)
            mentions.extend(
                _build_mentions_for_comments(rng, organization, bug_comments, commenters)
            )

            if rng.random() < profile["attachment_rate"]:
                attachments.extend(
                    _build_attachments_for_bug(rng, organization, bug, uploaders, created_at, now)
                )

            project._perf_bug_count += 1  # noqa: SLF001

        Bug.objects.bulk_create(bugs, batch_size=batch_size)
        for start in range(0, len(activities), batch_size):
            BugActivity.objects.bulk_create(
                activities[start : start + batch_size], batch_size=batch_size
            )
        for start in range(0, len(comments), batch_size):
            Comment.objects.bulk_create(comments[start : start + batch_size], batch_size=batch_size)
        for start in range(0, len(mentions), batch_size):
            Mention.objects.bulk_create(mentions[start : start + batch_size], batch_size=batch_size)
        for start in range(0, len(attachments), batch_size):
            Attachment.objects.bulk_create(
                attachments[start : start + batch_size], batch_size=batch_size
            )

        project._perf_activity_count = len(activities)  # noqa: SLF001
        project._perf_comment_count = len(comments)  # noqa: SLF001
        project._perf_mention_count = len(mentions)  # noqa: SLF001
        project._perf_attachment_count = len(attachments)  # noqa: SLF001

        # Advances the counter past every number just written, exactly the
        # way apps.bugs.services.create_bug would have left it after
        # `bug_count` real sequential creates — so a real create_bug() call
        # against this project afterward starts at bug_count + 1, not 1.
        Project.objects.filter(pk=project.pk).update(next_bug_number=bug_count + 1)

    def _build_notifications(
        self,
        rng: random.Random,
        organization: Organization,
        users: list,
        projects: list,
        profile: dict,
    ) -> list:
        """Concentrated among ~30% of users ("active" users) rather than
        spread evenly — matches "notifications concentrated among active
        users" from the requested distribution. Every notification
        references a real bug (and, for MENTIONED/COMMENT_ADDED, a real
        comment on that bug) belonging to the same organization as the
        recipient, satisfying both FK-ownership and the model's own
        comment-required CheckConstraint.
        """
        if not users or not projects:
            return []

        commented_bugs = list(
            Comment.objects.filter(organization=organization).values_list("bug_id", "id")
        )
        bugs_with_comments: dict = {}
        for bug_id, comment_id in commented_bugs:
            bugs_with_comments.setdefault(bug_id, []).append(comment_id)

        all_bug_ids = list(
            Bug.objects.filter(organization=organization).values_list("id", flat=True)
        )
        if not all_bug_ids:
            return []

        active_users = rng.sample(users, k=max(1, round(len(users) * 0.3)))
        notifications = []
        non_comment_events = [
            NotificationEventType.BUG_ASSIGNED,
            NotificationEventType.STATUS_CHANGED,
            NotificationEventType.BUG_REOPENED,
        ]
        comment_events = [NotificationEventType.MENTIONED, NotificationEventType.COMMENT_ADDED]
        bugs_with_comment_ids = list(bugs_with_comments.keys())

        for user in active_users:
            target = max(
                0,
                round(
                    rng.gauss(
                        profile["notifications_per_user"], profile["notifications_per_user"] / 3
                    )
                ),
            )
            # (recipient, dedup_key) must be unique per Notification's own
            # constraint — nothing about the random draws below prevents
            # picking the identical (event_type, comment) or a re-rolled
            # uuid4 twice for the same recipient by chance, especially at
            # small comment-pool sizes, so every candidate is checked
            # against this recipient's own already-used keys before being
            # added (and simply skipped, not retried, on a collision — a
            # slightly-under-target notification count for that one user is
            # harmless; the target is already itself only an average).
            used_keys_for_user: set[str] = set()
            for _ in range(target):
                use_comment_event = bool(bugs_with_comment_ids) and rng.random() < 0.5
                if use_comment_event:
                    event_type = rng.choice(comment_events)
                    bug_id = rng.choice(bugs_with_comment_ids)
                    comment_id = rng.choice(bugs_with_comments[bug_id])
                    dedup_key = f"{event_type}:{comment_id}"
                else:
                    event_type = rng.choice(non_comment_events)
                    bug_id = rng.choice(all_bug_ids)
                    comment_id = None
                    dedup_key = f"{event_type}:{uuid.uuid4()}"

                if dedup_key in used_keys_for_user:
                    continue
                used_keys_for_user.add(dedup_key)

                notifications.append(
                    Notification(
                        organization=organization,
                        recipient=user,
                        event_type=event_type,
                        actor=rng.choice(users),
                        bug_id=bug_id,
                        comment_id=comment_id,
                        dedup_key=dedup_key,
                        read_at=None if rng.random() < 0.4 else timezone.now(),
                        email_status="disabled",
                    )
                )
        return notifications

    # -- cleanup ------------------------------------------------------------

    def _cleanup(self) -> None:
        orgs = list(Organization.objects.filter(slug__startswith=PERF_SLUG_PREFIX))
        for org in orgs:
            if not org.slug.startswith(PERF_SLUG_PREFIX) or org.slug in PROTECTED_ORG_SLUGS:
                raise CommandError(
                    f"Refusing to clean up: organization {org.slug!r} does not look perf-owned. "
                    "This should be structurally impossible — aborting rather than deleting "
                    "anything."
                )

        if not orgs:
            self.stdout.write("No perf-owned organizations found — nothing to clean up.")
            return

        self.stdout.write(f"About to delete {len(orgs)} perf-owned organization(s):")
        for org in orgs:
            bug_count = Bug.objects.filter(organization=org).count()
            user_count = OrganizationMembership.objects.filter(organization=org).count()
            self.stdout.write(
                f"  - {org.slug} ({org.name}): {user_count} members, {bug_count} bugs."
            )

        user_ids = list(
            OrganizationMembership.objects.filter(organization__in=orgs).values_list(
                "user_id", flat=True
            )
        )

        with transaction.atomic():
            # Bug.project is on_delete=PROTECT (deliberately — see the
            # model's own comment: "a cascading delete here would only
            # ever be an accident, never a real user action to support"),
            # so Project (and therefore Organization, which cascades to
            # Project) cannot be deleted while any Bug still references
            # it, even though Bug.organization is itself CASCADE from
            # Organization. Bug rows must be deleted explicitly, first —
            # which itself cascades (CASCADE) to that bug's comments,
            # attachments, activities, notifications, and mentions. Only
            # once every Bug is gone does deleting the Organization
            # (cascading the now-bug-free Projects, memberships, and any
            # remaining organization-scoped rows) succeed.
            for org in orgs:
                Bug.objects.filter(organization=org).delete()
                org.delete()
            # Users are global (not organization-scoped) — only delete ones
            # that belonged *exclusively* to a deleted perf organization, so
            # a perf user who was somehow also added to a real organization
            # is never removed out from under it.
            orphaned = User.objects.filter(pk__in=user_ids).exclude(
                pk__in=OrganizationMembership.objects.values_list("user_id", flat=True)
            )
            deleted_users = orphaned.count()
            orphaned.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {len(orgs)} organization(s) and {deleted_users} orphaned user(s)."
            )
        )

    # -- reporting ------------------------------------------------------

    def _report(self, totals: dict, status_counts: dict, elapsed: float) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Performance dataset generated."))
        for key in (
            "organizations",
            "users",
            "memberships",
            "projects",
            "bugs",
            "activities",
            "comments",
            "mentions",
            "attachments",
            "notifications",
        ):
            self.stdout.write(f"  {key}: {totals[key]}")
        self.stdout.write(f"  elapsed: {elapsed:.1f}s")
        self.stdout.write("")
        self.stdout.write("Generated bug status distribution:")
        total_bugs = sum(status_counts.values()) or 1
        for status, count in sorted(status_counts.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"  {status}: {count} ({100 * count / total_bugs:.1f}%)")


# -- module-level helpers (no self needed) -----------------------------------


def _resolve_status_timestamps(rng: random.Random, *, status: str, created_at, now):
    """Reconstructs apps.bugs.workflow.apply_timestamp_side_effects' rules
    by hand: resolved_at is set for any resolution status and cleared for
    reopened; closed_at is set only for closed (and closed bugs keep the
    resolved_at they had *before* being closed, exactly like a real
    resolved -> closed transition would leave it). Also returns the two
    activity timestamps (resolution, reopen) so _build_activities_for_bug's
    STATUS_CHANGED rows land in the same chronological order as the
    timestamps on the Bug row itself — never generating a bug whose
    activity history contradicts its own resolved_at/closed_at.
    """
    if status in OPEN_STATUSES:
        return None, None, None, None

    if status == BugStatus.REOPENED:
        # Was resolved at some point *before* now, then reopened after
        # that — both events strictly between created_at and now.
        span = max((now - created_at).total_seconds(), 60)
        resolution_at = created_at + datetime.timedelta(seconds=rng.uniform(span * 0.2, span * 0.6))
        reopen_at = resolution_at + datetime.timedelta(seconds=rng.uniform(60, max(span * 0.3, 61)))
        if reopen_at > now:
            reopen_at = now
        return None, None, resolution_at, reopen_at

    span = max((now - created_at).total_seconds(), 60)
    resolved_at = created_at + datetime.timedelta(seconds=rng.uniform(span * 0.1, span * 0.9))
    if status == BugStatus.CLOSED:
        closed_at = resolved_at + datetime.timedelta(seconds=rng.uniform(60, max(span * 0.1, 61)))
        if closed_at > now:
            closed_at = now
        return resolved_at, closed_at, resolved_at, None
    return resolved_at, None, resolved_at, None


def _build_activities_for_bug(
    rng: random.Random,
    organization,
    bug,
    status,
    created_at,
    resolution_activity_at,
    reopen_activity_at,
    seed,
    *,
    target_count: float,
) -> list:
    activities = [
        BugActivity(
            organization=organization,
            bug=bug,
            actor=bug.reporter,
            verb=ActivityVerb.CREATED,
            to_value=bug.key,
            created_at=created_at,
            metadata={"perf_dataset": True, "seed": seed},
        )
    ]

    if status == BugStatus.REOPENED:
        activities.append(
            BugActivity(
                organization=organization,
                bug=bug,
                actor=bug.assignee or bug.reporter,
                verb=ActivityVerb.STATUS_CHANGED,
                from_value=BugStatus.IN_PROGRESS,
                to_value=BugStatus.RESOLVED,
                created_at=resolution_activity_at,
            )
        )
        activities.append(
            BugActivity(
                organization=organization,
                bug=bug,
                actor=bug.reporter,
                verb=ActivityVerb.STATUS_CHANGED,
                from_value=BugStatus.RESOLVED,
                to_value=BugStatus.REOPENED,
                created_at=reopen_activity_at,
            )
        )
    elif status != BugStatus.NEW:
        activities.append(
            BugActivity(
                organization=organization,
                bug=bug,
                actor=bug.assignee or bug.reporter,
                verb=ActivityVerb.STATUS_CHANGED,
                from_value=BugStatus.NEW,
                to_value=status,
                created_at=resolution_activity_at or (created_at + datetime.timedelta(hours=1)),
            )
        )

    # Non-status-changing padding, chronologically between created_at and
    # the bug's final activity, up to (roughly) target_count total rows.
    final_at = reopen_activity_at or resolution_activity_at or created_at
    padding_needed = max(0, round(target_count) - len(activities))
    for _ in range(padding_needed):
        verb = rng.choice(_ACTIVITY_PADDING_VERBS)
        span = max((final_at - created_at).total_seconds(), 1)
        at = created_at + datetime.timedelta(seconds=rng.uniform(0, span))
        activities.append(
            BugActivity(
                organization=organization,
                bug=bug,
                actor=bug.assignee or bug.reporter,
                verb=verb,
                from_value="",
                to_value="",
                created_at=at,
            )
        )

    return activities


_COMMENT_TEMPLATES = [
    "Can confirm, seeing the same thing on my end.",
    "Looking into this now.",
    "This looks related to the recent changes in this area — investigating.",
    "Reproduced locally. Steps match what's described above.",
    "Fixed in the latest deploy, please verify.",
    "Still happening after the last release.",
    "Adding more detail: this only happens under load.",
    "Thanks for the report — triaging now.",
]


def _build_comments_for_bug(
    rng: random.Random,
    organization,
    bug,
    commenters: list,
    created_at,
    now,
    *,
    target_average: float,
) -> list:
    if not commenters:
        return []
    # Most bugs: 0-3 comments. A small subset (~5%) is a "hot" bug with
    # many comments and activities — the long tail requested by Chunk I's
    # distribution shape. target_average only shifts the *mean*, not this
    # shape, since a fixed per-bug count would flatten the distribution
    # the spec explicitly asks for.
    if rng.random() < 0.05:
        count = rng.randint(10, 40)
    else:
        count = min(3, max(0, round(rng.gauss(target_average, 1.0))))

    comments = []
    span = max((now - created_at).total_seconds(), 60)
    timestamps = sorted(
        created_at + datetime.timedelta(seconds=rng.uniform(0, span)) for _ in range(count)
    )
    for at in timestamps:
        author = rng.choice(commenters)
        comments.append(
            Comment(
                organization=organization,
                bug=bug,
                author=author,
                body=rng.choice(_COMMENT_TEMPLATES),
                status=CommentStatus.ACTIVE,
                created_at=at,
                updated_at=at,
            )
        )
    return comments


def _build_mentions_for_comments(
    rng: random.Random, organization, comments: list, commenters: list
) -> list:
    if not comments or len(commenters) < 2:
        return []
    mentions = []
    for comment in comments:
        if rng.random() >= 0.15:
            continue
        candidates = [u for u in commenters if u.pk != comment.author_id]
        if not candidates:
            continue
        mentioned = rng.choice(candidates)
        display_name = f"{mentioned.first_name} {mentioned.last_name}".strip() or mentioned.email
        comment.body = f"{comment.body} @[{display_name}](mention:{mentioned.pk})"
        mentions.append(
            Mention(organization=organization, comment=comment, mentioned_user=mentioned)
        )
    return mentions


def _build_attachments_for_bug(
    rng: random.Random, organization, bug, uploaders: list, created_at, now
) -> list:
    """Metadata-only rows — see the module docstring's "Attachment
    metadata" section for why AttachmentStatus.FAILED is the safe choice:
    it requires no physical file (uploaded_at stays null, per the model's
    own CheckConstraint), and apps.attachments.selectors.
    list_attachments_for_bug filters to status=UPLOADED only, so these
    rows never appear in an ordinary attachment list or become
    downloadable — structurally, not by convention.
    """
    if not uploaders:
        return []
    count = 1 if rng.random() < 0.85 else rng.randint(2, 4)
    attachments = []
    for i in range(count):
        uploader = rng.choice(uploaders)
        failed_at = created_at + datetime.timedelta(
            seconds=rng.uniform(0, max((now - created_at).total_seconds(), 60))
        )
        attachments.append(
            Attachment(
                organization=organization,
                bug=bug,
                uploaded_by=uploader,
                original_filename=f"perf-fixture-{bug.key}-{i}.bin",
                content_type="application/octet-stream",
                size_bytes=rng.randint(1_024, 5_242_880),
                storage_key=f"perf/{bug.id}/{i}-{uuid.uuid4().hex}.bin",
                status=AttachmentStatus.FAILED,
                scan_status=ScanStatus.NOT_SCANNED,
                uploaded_at=None,
                failed_at=failed_at,
                removed_at=None,
                created_at=failed_at,
                updated_at=failed_at,
            )
        )
    return attachments
