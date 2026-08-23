import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.bugs.models import Bug, BugStatus
from apps.bugs.services import assign_bug, create_bug, transition_bug
from apps.core.demo_data import backdate_bug_history, due_date_days_ago
from apps.core.env import get_bool
from apps.organizations.models import (
    CommunityRole,
    Invitation,
    Organization,
    OrganizationMembership,
)
from apps.organizations.services import (
    InvitationAlreadyPending,
    MemberAlreadyExists,
    SetupAlreadyCompleted,
    SetupNotAllowed,
    accept_invitation,
    change_member_role,
    create_invitation,
    revoke_invitation,
    setup_instance,
)
from apps.projects.models import Project, ProjectStatus
from apps.projects.services import create_project, restore_project, update_project

User = get_user_model()

DEMO_ORG_NAME = "Quorfix Demo"
DEMO_ORG_SLUG = "quorfix-demo"

# Fixed, well-known, non-production credentials — intentionally hardcoded so
# every developer gets the exact same demo login. This command refuses to
# run under production-hardened settings (ENVIRONMENT == "production") at
# all unless QUORFIX_DISPOSABLE_DATABASE=true is explicitly set (see
# _seeding_permitted below) — the same opt-in flag
# apps.core.management.commands.generate_perf_dataset uses for the same
# purpose. Even then, the administrator persona's password below is never
# used as-is: _resolve_personas() requires an explicit DEMO_ADMIN_PASSWORD
# environment variable and substitutes it in, since that account carries
# real Django-admin and organization-admin power. The four non-admin
# personas keep these fixed, documented passwords even on a disposable demo
# deployment — that's the intended, publicly-documented demo login
# experience for exploring the product (see docs/ACCESS_AND_TESTING.md),
# and none of those roles can reach Django admin or manage members.
PERSONAS = [
    {
        "key": "admin",
        "email": "admin@quorfix.local",
        "first_name": "Demo",
        "last_name": "Administrator",
        "password": "QuorfixDemo2026!",
        "role": CommunityRole.ADMINISTRATOR,
    },
    {
        "key": "developer",
        "email": "developer@quorfix.local",
        "first_name": "Dev",
        "last_name": "User",
        "password": "DeveloperDemo2026!",
        "role": CommunityRole.DEVELOPER,
    },
    {
        "key": "qa",
        "email": "qa@quorfix.local",
        "first_name": "QA",
        "last_name": "Tester",
        "password": "QADemo2026!",
        "role": CommunityRole.QA,
    },
    {
        "key": "reporter",
        "email": "reporter@quorfix.local",
        "first_name": "Demo",
        "last_name": "Reporter",
        "password": "ReporterDemo2026!",
        "role": CommunityRole.REPORTER,
    },
    {
        "key": "viewer",
        "email": "viewer@quorfix.local",
        "first_name": "Demo",
        "last_name": "Viewer",
        "password": "ViewerDemo2026!",
        "role": CommunityRole.VIEWER,
    },
]

DEMO_PROJECTS = [
    {
        "name": "Quorfix Web Application",
        "key": "BFW",
        "status": ProjectStatus.ACTIVE,
        "lead": "admin",
    },
    {
        "name": "Mobile Application",
        "key": "MOB",
        "status": ProjectStatus.PLANNING,
        "lead": "developer",
    },
    {
        "name": "Legacy API",
        "key": "API",
        "status": ProjectStatus.ON_HOLD,
        "lead": "qa",
    },
]

# Looked up by (project, title) for idempotency — not by key/number, since
# those are assigned by the real sequential-numbering path in create_bug()
# and must never be guessed or forced by seed data (that's exactly the
# "don't manually force sequence counters into an inconsistent state"
# constraint). `transitions` is the ordered list of statuses walked from
# "new" via transition_bug(); `assignee`, when present, is applied first via
# assign_bug() so any ASSIGNED/IN_PROGRESS transition in the list already
# has an assignee to satisfy workflow.ASSIGNEE_REQUIRED_STATUSES.
#
# Phase 5 additions, for the analytics dashboard to have something
# meaningful to chart:
#   - created_days_ago backdates Bug.created_at (and its CREATED activity)
#     so bugs are spread across ~45 days instead of all landing on "now".
#   - resolution_days_ago is an ordered (oldest-first) list of day-offsets,
#     one per resolution-transition activity (verb=status_changed,
#     to_value in RESOLUTION_STATUSES) the bug's `transitions` walk
#     actually produces — most bugs have at most one; a bug that gets
#     reopened and resolved again has two, in order.
#   - closed_days_ago backdates Bug.closed_at (and its CLOSED activity)
#     for bugs whose `transitions` end in CLOSED.
#   - due_days_ago sets a due_date `due_days_ago` days in the past — used
#     for the one deliberately overdue demo bug.
# See apps.core.demo_data.backdate_bug_history for how these are applied;
# only ever via queryset.update() (bypassing auto_now_add), never by
# editing next_bug_number, number, key, or version.
DEMO_BUGS = [
    {
        "project": "BFW",
        "title": "Login button unresponsive on mobile Safari",
        "description": "Tapping 'Sign in' on iOS Safari does nothing on the first tap.",
        "reporter": "reporter",
        "priority": "high",
        "severity": "major",
        "category": "Frontend",
        "created_days_ago": 2,
    },
    {
        "project": "BFW",
        "title": "Dashboard chart fails to render for large datasets",
        "description": "Charts with more than ~500 points never finish loading.",
        "reporter": "reporter",
        "assignee": "developer",
        "priority": "urgent",
        "severity": "critical",
        "category": "Frontend",
        "transitions": [BugStatus.ASSIGNED],
        "created_days_ago": 4,
    },
    {
        "project": "BFW",
        "title": "Session expires while composing a comment",
        "description": "Long-form comments are lost if the session times out mid-edit.",
        "reporter": "qa",
        "assignee": "developer",
        "priority": "high",
        "severity": "major",
        "category": "Backend",
        "transitions": [BugStatus.ASSIGNED, BugStatus.IN_PROGRESS],
        "created_days_ago": 6,
    },
    {
        "project": "BFW",
        "title": "Exported CSV is missing the header row",
        "reporter": "reporter",
        "assignee": "qa",
        "priority": "medium",
        "severity": "minor",
        "category": "Data export",
        "transitions": [BugStatus.ASSIGNED, BugStatus.IN_PROGRESS, BugStatus.READY_FOR_QA],
        "created_days_ago": 9,
    },
    {
        "project": "BFW",
        "title": "Password reset email arrives several minutes late",
        "reporter": "reporter",
        "assignee": "developer",
        "priority": "high",
        "severity": "major",
        "category": "Notifications",
        "transitions": [BugStatus.ASSIGNED, BugStatus.IN_PROGRESS, BugStatus.RESOLVED],
        "created_days_ago": 15,
        "resolution_days_ago": [3],
    },
    {
        "project": "BFW",
        "title": "Footer copyright year is out of date",
        "reporter": "reporter",
        "assignee": "developer",
        "priority": "low",
        "severity": "trivial",
        "category": "Content",
        "transitions": [
            BugStatus.ASSIGNED,
            BugStatus.IN_PROGRESS,
            BugStatus.RESOLVED,
            BugStatus.CLOSED,
        ],
        "created_days_ago": 20,
        "resolution_days_ago": [10],
        "closed_days_ago": 4,
    },
    {
        "project": "BFW",
        "title": "Dashboard chart issue reported twice",
        "reporter": "reporter",
        "priority": "low",
        "severity": "minor",
        "category": "Frontend",
        "transitions": [BugStatus.DUPLICATE],
        "duplicate_of": "Dashboard chart fails to render for large datasets",
        "created_days_ago": 4,
        "resolution_days_ago": [3],
    },
    {
        "project": "MOB",
        "title": "App crashes when tapping a push notification",
        "reporter": "qa",
        "assignee": "developer",
        "priority": "urgent",
        "severity": "blocker",
        "category": "Crash",
        "transitions": [BugStatus.ASSIGNED, BugStatus.BLOCKED],
        "created_days_ago": 7,
    },
    {
        "project": "MOB",
        "title": "Onboarding flow skips step 3 on first launch",
        "reporter": "reporter",
        "priority": "medium",
        "severity": "major",
        "category": "Onboarding",
        "transitions": [BugStatus.TRIAGED],
        "created_days_ago": 11,
    },
    {
        "project": "API",
        "title": "Rate limit headers use the wrong header name",
        "reporter": "developer",
        "priority": "medium",
        "severity": "minor",
        "category": "API",
        "created_days_ago": 14,
    },
    {
        "project": "API",
        "title": "Legacy /v1/export endpoint returns 500 on an empty payload",
        "reporter": "qa",
        "assignee": "developer",
        "priority": "low",
        "severity": "minor",
        "category": "API",
        "transitions": [BugStatus.TRIAGED, BugStatus.WONT_FIX],
        "created_days_ago": 18,
        "resolution_days_ago": [9],
    },
    {
        "project": "API",
        "title": "Auth token refresh occasionally races the request queue",
        "reporter": "admin",
        "assignee": "developer",
        "priority": "high",
        "severity": "major",
        "category": "Auth",
        "transitions": [BugStatus.TRIAGED, BugStatus.CANNOT_REPRODUCE],
        "created_days_ago": 22,
        "resolution_days_ago": [11],
    },
    # -- Phase 5 additions: deferred/reopened statuses, an overdue bug, more
    # assignees and projects, and a resolve -> reopen -> resolve-again
    # history for the resolution-time/trend divergence to be visible.
    {
        "project": "BFW",
        "title": "User avatar upload silently fails above 2MB",
        "reporter": "reporter",
        "assignee": "qa",
        "priority": "medium",
        "severity": "major",
        "category": "Frontend",
        "transitions": [BugStatus.TRIAGED, BugStatus.DEFERRED],
        "created_days_ago": 13,
    },
    {
        "project": "BFW",
        "title": "Keyboard navigation skips the search field",
        "reporter": "reporter",
        "priority": "low",
        "severity": "minor",
        "category": "Accessibility",
        "created_days_ago": 1,
    },
    {
        "project": "BFW",
        "title": "Bulk bug export times out for large projects",
        "reporter": "qa",
        "assignee": "admin",
        "priority": "urgent",
        "severity": "critical",
        "category": "Performance",
        "transitions": [BugStatus.TRIAGED, BugStatus.ASSIGNED],
        "created_days_ago": 8,
        "due_days_ago": 5,
    },
    {
        "project": "BFW",
        "title": "Notification email uses wrong timezone",
        "reporter": "reporter",
        "assignee": "developer",
        "priority": "high",
        "severity": "major",
        "category": "Notifications",
        "transitions": [
            BugStatus.TRIAGED,
            BugStatus.IN_PROGRESS,
            BugStatus.RESOLVED,
            BugStatus.REOPENED,
        ],
        "created_days_ago": 25,
        "resolution_days_ago": [15],
    },
    {
        "project": "BFW",
        "title": "Search results pagination loses filters",
        "reporter": "reporter",
        "assignee": "developer",
        "priority": "low",
        "severity": "major",
        "category": "Frontend",
        "transitions": [
            BugStatus.TRIAGED,
            BugStatus.IN_PROGRESS,
            BugStatus.RESOLVED,
            BugStatus.REOPENED,
            BugStatus.IN_PROGRESS,
            BugStatus.RESOLVED,
        ],
        "created_days_ago": 40,
        "resolution_days_ago": [30, 5],
    },
    {
        "project": "MOB",
        "title": "Push token refresh loop drains battery",
        "reporter": "qa",
        "assignee": "developer",
        "priority": "urgent",
        "severity": "blocker",
        "category": "Performance",
        "transitions": [BugStatus.TRIAGED, BugStatus.IN_PROGRESS],
        "created_days_ago": 3,
    },
    {
        "project": "MOB",
        "title": "Deep link fails to open correct screen",
        "reporter": "reporter",
        "priority": "medium",
        "severity": "minor",
        "category": "Navigation",
        "transitions": [BugStatus.TRIAGED],
        "created_days_ago": 6,
    },
    {
        "project": "MOB",
        "title": "App icon badge count is inaccurate",
        "reporter": "reporter",
        "assignee": "qa",
        "priority": "low",
        "severity": "trivial",
        "category": "Notifications",
        "transitions": [
            BugStatus.TRIAGED,
            BugStatus.ASSIGNED,
            BugStatus.IN_PROGRESS,
            BugStatus.READY_FOR_QA,
            BugStatus.RESOLVED,
            BugStatus.CLOSED,
        ],
        "created_days_ago": 35,
        "resolution_days_ago": [20],
        "closed_days_ago": 10,
    },
    {
        "project": "API",
        "title": "Webhook retries do not use exponential backoff",
        "reporter": "developer",
        "assignee": "admin",
        "priority": "high",
        "severity": "major",
        "category": "Integrations",
        "transitions": [BugStatus.TRIAGED, BugStatus.IN_PROGRESS],
        "created_days_ago": 5,
    },
    {
        "project": "API",
        "title": "Pagination cursor breaks on deleted records",
        "reporter": "qa",
        "priority": "medium",
        "severity": "major",
        "category": "API",
        "transitions": [BugStatus.TRIAGED, BugStatus.BLOCKED],
        "created_days_ago": 17,
    },
    {
        "project": "API",
        "title": "GraphQL schema introspection exposes internal fields",
        "reporter": "admin",
        "assignee": "developer",
        "priority": "urgent",
        "severity": "critical",
        "category": "Security",
        "transitions": [BugStatus.TRIAGED, BugStatus.IN_PROGRESS, BugStatus.RESOLVED],
        "created_days_ago": 12,
        "resolution_days_ago": [2],
    },
    {
        "project": "API",
        "title": "Duplicate webhook events sent on retry",
        "reporter": "reporter",
        "priority": "low",
        "severity": "minor",
        "category": "Integrations",
        "created_days_ago": 1,
    },
]


def _is_production_settings() -> bool:
    # Matches apps.core.checks._is_production() and
    # generate_perf_dataset._is_production_settings() — ENVIRONMENT is set
    # literally per settings module (never environment-derived), so this
    # can't be flipped by a stray env var the way parsing SETTINGS_MODULE's
    # string could be.
    return settings.ENVIRONMENT == "production"


def _seeding_permitted() -> bool:
    """Development/test may always seed. A production-hardened deployment
    (the demo included, since it needs the same DEBUG=False/secure-cookie
    settings as real production) may only seed if it has explicitly opted
    in via QUORFIX_DISPOSABLE_DATABASE=true — the same flag
    generate_perf_dataset uses to mean "this specific database holds no
    real customer data." A real production/customer deployment has no
    reason to ever set it."""
    if not _is_production_settings():
        return True
    return get_bool("QUORFIX_DISPOSABLE_DATABASE", False)


class Command(BaseCommand):
    help = (
        "Seeds demo data: one organization, five demo users (one per Community "
        "role), three projects, and sample bugs. Idempotent — safe to re-run. "
        "Refuses to run under production-hardened settings unless "
        "QUORFIX_DISPOSABLE_DATABASE=true is explicitly set (and, when it is, "
        "requires DEMO_ADMIN_PASSWORD instead of the documented development "
        "admin password). Refuses to run if a different organization is "
        "already configured (Community allows only one)."
    )

    def handle(self, *args, **options):
        if not _seeding_permitted():
            raise CommandError(
                "seed_demo refuses to run against a production-hardened deployment "
                "(ENVIRONMENT='production') unless QUORFIX_DISPOSABLE_DATABASE=true is "
                "explicitly set in the environment. This command creates well-known, "
                "publicly-documented demo accounts and must never touch a real "
                "customer/production database — only set this flag for a dedicated, "
                "isolated, disposable demo deployment. See docs/ACCESS_AND_TESTING.md."
            )

        personas = self._resolve_personas()

        organization = self._ensure_organization(personas)

        users = {}
        for persona in personas:
            users[persona["key"]] = self._ensure_member(organization, persona, personas)

        for spec in DEMO_PROJECTS:
            self._ensure_project(organization, spec, lead=users[spec["lead"]])
        projects = {
            spec["key"]: Project.objects.get(organization=organization, key=spec["key"])
            for spec in DEMO_PROJECTS
        }

        self._ensure_bugs(organization, projects, users, reference_now=timezone.now())

        self._report(organization, personas)

    def _resolve_personas(self) -> list[dict]:
        """Returns the persona list to actually seed with. On a
        production-hardened deployment (the demo), the fixed, publicly-
        documented QuorfixDemo2026! admin password must never be reachable
        — this substitutes it for an explicit, deployment-supplied value
        instead. The other four personas are unaffected; see the PERSONAS
        comment for why."""
        if not _is_production_settings():
            return PERSONAS

        admin_password = os.environ.get("DEMO_ADMIN_PASSWORD", "").strip()
        if not admin_password:
            raise CommandError(
                "DEMO_ADMIN_PASSWORD must be set to seed the administrator account on "
                "a production-hardened (demo) deployment. The documented "
                "QuorfixDemo2026! password is for local development only and is never "
                "used here — set DEMO_ADMIN_PASSWORD to a unique value generated for "
                "this deployment before seeding."
            )
        return [
            {**persona, "password": admin_password} if persona["key"] == "admin" else persona
            for persona in PERSONAS
        ]

    # -- organization -----------------------------------------------------

    def _ensure_organization(self, personas: list[dict]) -> Organization:
        organization = Organization.objects.filter(slug=DEMO_ORG_SLUG).first()
        if organization is not None:
            self.stdout.write(f"Organization '{organization.slug}' already exists — reusing it.")
            return organization

        admin_persona = next(p for p in personas if p["key"] == "admin")
        try:
            _user, organization, _membership = setup_instance(
                organization_name=DEMO_ORG_NAME,
                email=admin_persona["email"],
                password=admin_persona["password"],
                first_name=admin_persona["first_name"],
                last_name=admin_persona["last_name"],
            )
        except SetupAlreadyCompleted as exc:
            raise CommandError(
                "This instance is already configured with a different organization. "
                "Community allows only one active organization, so demo data can't be "
                "seeded here without first resetting the database."
            ) from exc
        except SetupNotAllowed as exc:
            raise CommandError(
                "Creating the demo organization is not allowed — an organization "
                "already exists and multiple organizations aren't enabled."
            ) from exc

        if organization.slug != DEMO_ORG_SLUG:
            # Would only happen if a differently-slugged organization already
            # collided with "Quorfix Demo"'s slugified name — don't
            # silently seed data under an unexpected slug.
            raise CommandError(
                f"Created organization slug {organization.slug!r} does not match the "
                f"expected demo slug {DEMO_ORG_SLUG!r}."
            )

        self.stdout.write(f"Created organization '{organization.name}' ({organization.slug}).")
        return organization

    # -- members ------------------------------------------------------------

    def _ensure_member(self, organization: Organization, persona: dict, personas: list[dict]):
        email = persona["email"].lower()

        membership = (
            OrganizationMembership.objects.select_related("user")
            .filter(organization=organization, user__email=email)
            .first()
        )

        if membership is not None:
            self._sync_persona(membership.user, persona)
            if membership.role != persona["role"]:
                # bypass_demo_protection=True: this command owns these five
                # personas — apps.organizations.services blocks any other
                # caller from changing a demo persona's role at all (see
                # apps.accounts.services.is_demo_user), which would
                # otherwise make role-drift reconvergence impossible here.
                membership = change_member_role(
                    membership=membership,
                    new_role=persona["role"],
                    bypass_demo_protection=True,
                )
                self.stdout.write(f"Updated role for {email} -> {persona['role']}.")
            else:
                self.stdout.write(f"Member {email} already up to date.")
            return membership.user

        user = self._invite_and_accept(organization, persona, email, personas)
        self._sync_persona(user, persona)
        self.stdout.write(f"Created member {email} ({persona['role']}).")
        return user

    def _invite_and_accept(
        self, organization: Organization, persona: dict, email: str, personas: list[dict]
    ):
        # Goes through the same invite -> accept path a real teammate would,
        # so seeding stays on the business-rule-enforced path (role
        # validation, membership creation) rather than constructing
        # memberships directly.
        admin_persona = next(p for p in personas if p["key"] == "admin")
        invited_by = User.objects.filter(email=admin_persona["email"].lower()).first()

        # bypass_demo_protection=True at both call sites below: this command
        # is the one place that legitimately creates the five demo personas
        # via the invite -> accept path — apps.organizations.services
        # otherwise blocks every invitation into the "quorfix-demo"
        # organization (see apps.accounts.services.DEMO_ORGANIZATION_SLUG),
        # which would make first-time seeding impossible without it.
        try:
            _invitation, raw_token = create_invitation(
                organization=organization,
                invited_by=invited_by,
                email=email,
                role=persona["role"],
                bypass_demo_protection=True,
            )
        except MemberAlreadyExists:
            # Became a member between the check in _ensure_member and here.
            membership = OrganizationMembership.objects.select_related("user").get(
                organization=organization, user__email=email
            )
            return membership.user
        except InvitationAlreadyPending:
            # Leftover from an earlier interrupted run — revoke it and retry
            # once, using the same revoke_invitation service the API uses.
            stale = Invitation.objects.get(
                organization=organization,
                email=email,
                accepted_at__isnull=True,
                revoked_at__isnull=True,
            )
            revoke_invitation(invitation=stale)
            _invitation, raw_token = create_invitation(
                organization=organization,
                invited_by=invited_by,
                email=email,
                role=persona["role"],
                bypass_demo_protection=True,
            )

        user, _membership = accept_invitation(
            raw_token=raw_token,
            password=persona["password"],
            first_name=persona["first_name"],
            last_name=persona["last_name"],
        )
        return user

    def _sync_persona(self, user, persona: dict) -> None:
        """Converges an existing user's profile/password to the persona spec.

        No dedicated service exists for "reset a user's profile to a known
        value" — that's not real app behavior, only a seeding concern — so
        this updates the model directly, gated (like everything else in this
        command) by the production guard in handle().
        """
        update_fields = []
        if user.first_name != persona["first_name"]:
            user.first_name = persona["first_name"]
            update_fields.append("first_name")
        if user.last_name != persona["last_name"]:
            user.last_name = persona["last_name"]
            update_fields.append("last_name")
        if not user.check_password(persona["password"]):
            user.set_password(persona["password"])
            update_fields.append("password")
        if update_fields:
            user.save(update_fields=update_fields)

    # -- projects -------------------------------------------------------

    def _ensure_project(self, organization: Organization, spec: dict, lead) -> None:
        project = Project.objects.filter(organization=organization, key=spec["key"]).first()

        if project is None:
            create_project(
                organization=organization,
                name=spec["name"],
                key=spec["key"],
                status=spec["status"],
                lead=lead,
            )
            self.stdout.write(f"Created project {spec['key']} — {spec['name']}.")
            return

        if project.archived_at is not None:
            project = restore_project(project=project)

        needs_update = (
            project.name != spec["name"]
            or project.status != spec["status"]
            or project.lead_id != lead.pk
        )
        if needs_update:
            update_project(project=project, name=spec["name"], status=spec["status"], lead=lead)
            self.stdout.write(f"Updated project {spec['key']}.")
        else:
            self.stdout.write(f"Project {spec['key']} already up to date.")

    # -- bugs -------------------------------------------------------------

    def _ensure_bugs(
        self, organization: Organization, projects: dict, users: dict, *, reference_now
    ) -> None:
        admin_user = users["admin"]
        admin_membership = OrganizationMembership.objects.get(
            organization=organization, user=admin_user
        )
        bugs_by_title: dict[str, Bug] = {}

        for spec in DEMO_BUGS:
            bugs_by_title[spec["title"]] = self._ensure_bug(
                organization,
                projects[spec["project"]],
                users,
                admin_user,
                admin_membership,
                spec,
                bugs_by_title,
                reference_now=reference_now,
            )

    def _ensure_bug(
        self,
        organization: Organization,
        project: Project,
        users: dict,
        admin_user,
        admin_membership,
        spec: dict,
        bugs_by_title: dict,
        *,
        reference_now,
    ) -> Bug:
        # Looked up by (project, title) — never by key/number, since those
        # come only from create_bug()'s real sequential-numbering path.
        # Skipping entirely when found (rather than reconciling status like
        # _ensure_project does) keeps this idempotent without ever writing
        # to Bug.version or Project.next_bug_number outside that path.
        existing = Bug.objects.filter(
            organization=organization, project=project, title=spec["title"]
        ).first()
        if existing is not None:
            self.stdout.write(f"Bug '{spec['title']}' already exists in {project.key} — skipping.")
            return existing

        reporter = users[spec["reporter"]]
        reporter_membership = OrganizationMembership.objects.get(
            organization=organization, user=reporter
        )

        bug = create_bug(
            organization=organization,
            project=project,
            reporter=reporter,
            membership=reporter_membership,
            title=spec["title"],
            description=spec.get("description", ""),
            category=spec.get("category", ""),
            priority=spec.get("priority", "medium"),
            severity=spec.get("severity", "major"),
            due_date=due_date_days_ago(spec.get("due_days_ago")),
        )

        assignee_key = spec.get("assignee")
        if assignee_key:
            bug = assign_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                assignee_id=str(users[assignee_key].pk),
                expected_version=bug.version,
            )

        for target_status in spec.get("transitions", []):
            kwargs = {}
            if target_status == BugStatus.DUPLICATE:
                kwargs["duplicate_of"] = str(bugs_by_title[spec["duplicate_of"]].pk)
            bug = transition_bug(
                bug=bug,
                actor=admin_user,
                membership=admin_membership,
                new_status=target_status,
                expected_version=bug.version,
                **kwargs,
            )

        backdate_bug_history(
            bug,
            reference_now=reference_now,
            created_days_ago=spec.get("created_days_ago"),
            resolution_days_ago=spec.get("resolution_days_ago"),
            closed_days_ago=spec.get("closed_days_ago"),
        )

        self.stdout.write(f"Created bug {bug.key} — {spec['title']} ({bug.status}).")
        return bug

    # -- reporting ------------------------------------------------------

    def _report(self, organization: Organization, personas: list[dict]) -> None:
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"Demo data ready for organization '{organization.name}'.")
        )
        self.stdout.write(f"Application URL: {settings.FRONTEND_BASE_URL}")

        if not settings.DEBUG:
            self.stdout.write(
                "DEBUG is off for the active settings module — skipping credential output. "
                "Re-run with development settings to see demo login details."
            )
            return

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "DEVELOPMENT-ONLY ACCOUNTS. Do not reuse these credentials anywhere but a "
                "local development environment, and never seed or expose them in production."
            )
        )
        self.stdout.write("")

        rows = [(p["role"], p["email"], p["password"]) for p in personas]
        role_width = max(len("Role"), *(len(r[0]) for r in rows))
        email_width = max(len("Email"), *(len(r[1]) for r in rows))
        password_width = max(len("Password"), *(len(r[2]) for r in rows))

        header = f"{'Role':<{role_width}}  {'Email':<{email_width}}  {'Password':<{password_width}}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for role, email, password in rows:
            self.stdout.write(
                f"{role:<{role_width}}  {email:<{email_width}}  {password:<{password_width}}"
            )
        self.stdout.write("")
