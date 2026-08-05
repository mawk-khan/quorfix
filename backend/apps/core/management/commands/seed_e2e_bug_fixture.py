from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
from apps.projects.models import Project
from apps.projects.services import create_project

User = get_user_model()

# Deliberately namespaced ("bug-e2e-...") so these never collide with any
# other spec file's fixtures (team-journey.spec.ts's "Acme"/admin@example.com,
# team-project-lifecycle.spec.ts's project-viewer@example.com, etc.) — every
# email here is globally unique across the whole Playwright run regardless
# of which spec files execute, or in what order.
ORG_NAME = "Bug E2E Org"
ORG_SLUG = "bug-e2e-org"
PROJECT_KEY = "BEP"
PROJECT_NAME = "Bug E2E Project"
PASSWORD = "BugE2EPass123!"

PERSONAS = [
    {"key": "admin", "email": "bug-e2e-admin@example.com", "role": CommunityRole.ADMINISTRATOR},
    {"key": "developer", "email": "bug-e2e-developer@example.com", "role": CommunityRole.DEVELOPER},
    {"key": "qa", "email": "bug-e2e-qa@example.com", "role": CommunityRole.QA},
    {"key": "reporter", "email": "bug-e2e-reporter@example.com", "role": CommunityRole.REPORTER},
    {"key": "viewer", "email": "bug-e2e-viewer@example.com", "role": CommunityRole.VIEWER},
]


def _is_production_settings() -> bool:
    settings_module = getattr(settings, "SETTINGS_MODULE", "") or ""
    return settings_module.rsplit(".", 1)[-1] == "production"


class Command(BaseCommand):
    help = (
        "Seeds a small, dedicated organization/users/project fixture for the "
        "Playwright bug-lifecycle spec (e2e/bug-lifecycle.spec.ts) — deliberately "
        "independent of whatever other spec files create (Acme, project-viewer@..., "
        "etc.), so that spec never depends on file-execution order. Idempotent: "
        "safe to call multiple times. Refuses to run under production settings, "
        "matching seed_demo."
    )

    def handle(self, *args, **options):
        if _is_production_settings():
            raise CommandError(
                "seed_e2e_bug_fixture refuses to run with production settings "
                f"(SETTINGS_MODULE={settings.SETTINGS_MODULE!r}). This command creates "
                "well-known, publicly-documented test accounts and must never touch a "
                "production database."
            )

        # is_active=False deliberately: OrganizationPolicy.can_create_additional_organization()
        # (the gate behind the real /setup flow) checks Organization.objects.filter(is_active=True)
        # — an active row here would silently block team-journey.spec.ts's own first-run-setup
        # test for the rest of the Playwright run. Nothing else in the codebase reads is_active
        # (confirmed: it's the only call site), so this organization remains fully functional for
        # authentication, membership, and every bug/project operation — it just stays invisible
        # to that one check, which is all "not a second real product organization" needs to mean.
        organization, _ = Organization.objects.get_or_create(
            slug=ORG_SLUG, defaults={"name": ORG_NAME, "is_active": False}
        )

        users = {}
        for persona in PERSONAS:
            user, created = User.objects.get_or_create(
                email=persona["email"],
                defaults={
                    "username": f"bug-e2e-{persona['key']}",
                    "first_name": "E2E",
                    "last_name": persona["key"].title(),
                },
            )
            if created:
                user.set_password(PASSWORD)
                user.save(update_fields=["password"])
            OrganizationMembership.objects.get_or_create(
                organization=organization, user=user, defaults={"role": persona["role"]}
            )
            users[persona["key"]] = user
            self.stdout.write(f"Ensured {persona['email']} ({persona['role']}).")

        project = Project.objects.filter(organization=organization, key=PROJECT_KEY).first()
        if project is None:
            project = create_project(
                organization=organization,
                name=PROJECT_NAME,
                key=PROJECT_KEY,
                lead=users["admin"],
            )
            self.stdout.write(f"Created project {PROJECT_KEY}.")
        else:
            self.stdout.write(f"Project {PROJECT_KEY} already exists.")

        self.stdout.write(
            self.style.SUCCESS(f"E2E bug fixture ready in organization '{ORG_NAME}'.")
        )
