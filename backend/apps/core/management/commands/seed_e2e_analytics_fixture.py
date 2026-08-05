from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.bugs.models import Bug, BugStatus
from apps.bugs.services import assign_bug, create_bug, transition_bug
from apps.core.demo_data import backdate_bug_history, due_date_days_ago
from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
from apps.projects.models import Project
from apps.projects.services import create_project

User = get_user_model()

# Deliberately namespaced ("analytics-e2e-...") so these never collide with
# any other spec file's fixtures (team-journey.spec.ts's "Acme", bug-
# lifecycle.spec.ts's "bug-e2e-...", etc.) — every email here is globally
# unique across the whole Playwright run regardless of which spec files
# execute, or in what order.
ORG_NAME = "Analytics E2E Org"
ORG_SLUG = "analytics-e2e-org"
PROJECT_KEY = "ANLY"
PROJECT_NAME = "Analytics E2E Project"
PASSWORD = "AnalyticsE2EPass123!"

PERSONAS = [
    {
        "key": "admin",
        "email": "analytics-e2e-admin@example.com",
        "role": CommunityRole.ADMINISTRATOR,
    },
    {
        "key": "developer",
        "email": "analytics-e2e-developer@example.com",
        "role": CommunityRole.DEVELOPER,
    },
    {"key": "qa", "email": "analytics-e2e-qa@example.com", "role": CommunityRole.QA},
    {
        "key": "reporter",
        "email": "analytics-e2e-reporter@example.com",
        "role": CommunityRole.REPORTER,
    },
    {"key": "viewer", "email": "analytics-e2e-viewer@example.com", "role": CommunityRole.VIEWER},
]

# Deliberately small (8 bugs) and every day-offset chosen with a safety
# margin around the 7-day preset's boundary (offset 6 is the last day
# INSIDE "last 7 days" per the "today + previous 6 days" convention — see
# frontend's date-preset helper): every value meant to land INSIDE stays
# <=5, every value meant to land OUTSIDE stays >=8. This survives the
# fixture-seed-time and test-run-time "today" differing by up to a day
# (see global-setup.ts) without any assertion crossing the boundary.
#
# Expected dashboard values with this fixture (asserted directly in
# e2e/dashboard.spec.ts — recomputed here for anyone auditing this file):
#   open_bugs = 5, overdue_bugs = 1
#   last-7-days:  new_bugs = 6, resolved_bugs = 1
#   last-30-days: new_bugs = 8, resolved_bugs = 3
#   status distribution: new=1 triaged=1 assigned=1 in_progress=1
#                         resolved=2 wont_fix=1 blocked=1
#   severity distribution: major=3 critical=1 minor=2 trivial=1 blocker=1
#   workload: developer=1, qa=1, unassigned=3
#   active projects: 1 (ANLY), total_bugs=8, open_bugs=5
FIXTURE_BUGS = [
    {
        "title": "E2E Login page renders blank on slow network",
        "reporter": "reporter",
        "priority": "high",
        "severity": "major",
        "created_days_ago": 1,
    },
    {
        "title": "E2E Dashboard totals mismatch on refresh",
        "reporter": "reporter",
        "priority": "medium",
        "severity": "minor",
        "transitions": [BugStatus.TRIAGED],
        "created_days_ago": 2,
    },
    {
        "title": "E2E Assignee avatar missing on bug card",
        "reporter": "qa",
        "assignee": "developer",
        "priority": "urgent",
        "severity": "critical",
        "transitions": [BugStatus.ASSIGNED],
        "created_days_ago": 3,
        "due_days_ago": 3,
    },
    {
        "title": "E2E Search filter resets unexpectedly",
        "reporter": "reporter",
        "assignee": "qa",
        "priority": "medium",
        "severity": "major",
        "transitions": [BugStatus.ASSIGNED, BugStatus.IN_PROGRESS],
        "created_days_ago": 4,
    },
    {
        "title": "E2E Export button double-submits",
        "reporter": "reporter",
        "assignee": "developer",
        "priority": "high",
        "severity": "major",
        "transitions": [BugStatus.ASSIGNED, BugStatus.IN_PROGRESS, BugStatus.RESOLVED],
        "created_days_ago": 5,
        "resolution_days_ago": [1],
    },
    {
        "title": "E2E Old cache invalidation bug",
        "reporter": "qa",
        "assignee": "qa",
        "priority": "low",
        "severity": "minor",
        "transitions": [BugStatus.ASSIGNED, BugStatus.IN_PROGRESS, BugStatus.RESOLVED],
        "created_days_ago": 20,
        "resolution_days_ago": [15],
    },
    {
        "title": "E2E Tag color contrast too low",
        "reporter": "reporter",
        "priority": "low",
        "severity": "trivial",
        "transitions": [BugStatus.TRIAGED, BugStatus.WONT_FIX],
        "created_days_ago": 12,
        "resolution_days_ago": [9],
    },
    {
        "title": "E2E Blocked import job",
        "reporter": "admin",
        "priority": "high",
        "severity": "blocker",
        "transitions": [BugStatus.TRIAGED, BugStatus.BLOCKED],
        "created_days_ago": 4,
    },
]


def _is_production_settings() -> bool:
    settings_module = getattr(settings, "SETTINGS_MODULE", "") or ""
    return settings_module.rsplit(".", 1)[-1] == "production"


class Command(BaseCommand):
    help = (
        "Seeds a small, dedicated organization/users/project/bugs fixture for the "
        "Playwright analytics dashboard spec (e2e/dashboard.spec.ts) — deliberately "
        "independent of whatever other spec files create, so that spec never depends "
        "on file-execution order. Idempotent: safe to call multiple times (bugs are "
        "only ever created, and therefore only ever backdated, once). Refuses to run "
        "under production settings, matching seed_demo and seed_e2e_bug_fixture."
    )

    def handle(self, *args, **options):
        if _is_production_settings():
            raise CommandError(
                "seed_e2e_analytics_fixture refuses to run with production settings "
                f"(SETTINGS_MODULE={settings.SETTINGS_MODULE!r}). This command creates "
                "well-known, publicly-documented test accounts and must never touch a "
                "production database."
            )

        # is_active=False for the same reason seed_e2e_bug_fixture uses it:
        # OrganizationPolicy.can_create_additional_organization() only looks
        # at is_active=True organizations, so this stays invisible to the
        # "only one active organization" check other specs (team-journey's
        # first-run setup) depend on, while remaining fully usable for
        # authentication and every bug/project operation.
        organization, _ = Organization.objects.get_or_create(
            slug=ORG_SLUG, defaults={"name": ORG_NAME, "is_active": False}
        )

        users = {}
        memberships = {}
        for persona in PERSONAS:
            user, created = User.objects.get_or_create(
                email=persona["email"],
                defaults={
                    "username": f"analytics-e2e-{persona['key']}",
                    "first_name": "Analytics E2E",
                    "last_name": persona["key"].title(),
                },
            )
            if created:
                user.set_password(PASSWORD)
                user.save(update_fields=["password"])
            membership, _ = OrganizationMembership.objects.get_or_create(
                organization=organization, user=user, defaults={"role": persona["role"]}
            )
            users[persona["key"]] = user
            memberships[persona["key"]] = membership
            self.stdout.write(f"Ensured {persona['email']} ({persona['role']}).")

        project = Project.objects.filter(organization=organization, key=PROJECT_KEY).first()
        if project is None:
            project = create_project(
                organization=organization, name=PROJECT_NAME, key=PROJECT_KEY, lead=users["admin"]
            )
            self.stdout.write(f"Created project {PROJECT_KEY}.")
        else:
            self.stdout.write(f"Project {PROJECT_KEY} already exists.")

        # One reference instant for the whole run — every bug's offsets are
        # computed from this single timestamp, not repeated timezone.now()
        # calls, so the fixture's internal relative-day math can't drift
        # against itself even if the command happens to straddle midnight.
        reference_now = timezone.now()
        admin_membership = memberships["admin"]
        for spec in FIXTURE_BUGS:
            self._ensure_bug(organization, project, users, admin_membership, spec, reference_now)

        self.stdout.write(self.style.SUCCESS(f"Analytics E2E fixture ready in '{ORG_NAME}'."))

    def _ensure_bug(self, organization, project, users, admin_membership, spec, reference_now):
        existing = Bug.objects.filter(
            organization=organization, project=project, title=spec["title"]
        ).first()
        if existing is not None:
            self.stdout.write(f"Bug '{spec['title']}' already exists — skipping.")
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
            priority=spec.get("priority", "medium"),
            severity=spec.get("severity", "major"),
            due_date=due_date_days_ago(spec.get("due_days_ago")),
        )

        assignee_key = spec.get("assignee")
        if assignee_key:
            bug = assign_bug(
                bug=bug,
                actor=users["admin"],
                membership=admin_membership,
                assignee_id=str(users[assignee_key].pk),
                expected_version=bug.version,
            )

        for target_status in spec.get("transitions", []):
            bug = transition_bug(
                bug=bug,
                actor=users["admin"],
                membership=admin_membership,
                new_status=target_status,
                expected_version=bug.version,
            )

        backdate_bug_history(
            bug,
            reference_now=reference_now,
            created_days_ago=spec.get("created_days_ago"),
            resolution_days_ago=spec.get("resolution_days_ago"),
        )

        self.stdout.write(f"Created bug {bug.key} — {spec['title']} ({bug.status}).")
        return bug
