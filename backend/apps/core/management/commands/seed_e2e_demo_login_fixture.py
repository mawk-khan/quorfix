from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services import DEMO_ORGANIZATION_SLUG, DEMO_ROLE_TO_EMAIL
from apps.organizations.models import Organization, OrganizationMembership

User = get_user_model()

ORG_NAME = "Quorfix Demo"
# A fixed, non-secret password — never used by the Playwright spec this
# fixture backs (e2e/demo-login.spec.ts exercises the password-less
# DemoLoginView exclusively), kept only so these accounts remain usable for
# ordinary email/password sign-in during manual local review too.
PASSWORD = "DemoLoginE2EPass123!"


def _is_production_settings() -> bool:
    settings_module = getattr(settings, "SETTINGS_MODULE", "") or ""
    return settings_module.rsplit(".", 1)[-1] == "production"


class Command(BaseCommand):
    help = (
        "Seeds the 'Quorfix Demo' organization (slug quorfix-demo) and its five "
        "fixed personas for the Playwright demo-login spec (e2e/demo-login.spec.ts) "
        "— the exact organization/emails apps.accounts.services.resolve_demo_login_user "
        "requires. Idempotent: safe to call multiple times, and safe alongside "
        "seed_demo (matching email + org slug means it simply reuses whatever seed_demo "
        "already created). Refuses to run under production settings, matching seed_demo."
    )

    def handle(self, *args, **options):
        if _is_production_settings():
            raise CommandError(
                "seed_e2e_demo_login_fixture refuses to run with production settings "
                f"(SETTINGS_MODULE={settings.SETTINGS_MODULE!r}). This command creates "
                "well-known, publicly-documented test accounts and must never touch a "
                "production database."
            )

        # is_active=False, same reasoning as seed_e2e_bug_fixture: keeps this
        # organization invisible to OrganizationPolicy.can_create_additional_organization()
        # (the gate behind the real /setup flow), so it never blocks
        # team-journey.spec.ts's first-run-setup test regardless of run order.
        organization, _ = Organization.objects.get_or_create(
            slug=DEMO_ORGANIZATION_SLUG, defaults={"name": ORG_NAME, "is_active": False}
        )

        for role, email in DEMO_ROLE_TO_EMAIL.items():
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": f"demo-login-e2e-{role}",
                    "first_name": "Demo",
                    "last_name": role.title(),
                },
            )
            if created:
                user.set_password(PASSWORD)
                user.save(update_fields=["password"])
            OrganizationMembership.objects.get_or_create(
                organization=organization, user=user, defaults={"role": role}
            )
            self.stdout.write(f"Ensured {email} ({role}).")

        self.stdout.write(
            self.style.SUCCESS(f"E2E demo-login fixture ready in organization '{ORG_NAME}'.")
        )
