from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

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

DEMO_ORG_NAME = "Bug Fixer Demo"
DEMO_ORG_SLUG = "bug-fixer-demo"

# Fixed, well-known, non-production credentials — intentionally hardcoded so
# every developer gets the exact same demo login. This command refuses to
# run under production settings (see _is_production_settings below), so
# these values are never reachable outside a local/dev database.
PERSONAS = [
    {
        "key": "admin",
        "email": "admin@bugfixer.local",
        "first_name": "Demo",
        "last_name": "Administrator",
        "password": "BugFixerDemo2026!",
        "role": CommunityRole.ADMINISTRATOR,
    },
    {
        "key": "developer",
        "email": "developer@bugfixer.local",
        "first_name": "Dev",
        "last_name": "User",
        "password": "DeveloperDemo2026!",
        "role": CommunityRole.DEVELOPER,
    },
    {
        "key": "qa",
        "email": "qa@bugfixer.local",
        "first_name": "QA",
        "last_name": "Tester",
        "password": "QADemo2026!",
        "role": CommunityRole.QA,
    },
    {
        "key": "reporter",
        "email": "reporter@bugfixer.local",
        "first_name": "Demo",
        "last_name": "Reporter",
        "password": "ReporterDemo2026!",
        "role": CommunityRole.REPORTER,
    },
    {
        "key": "viewer",
        "email": "viewer@bugfixer.local",
        "first_name": "Demo",
        "last_name": "Viewer",
        "password": "ViewerDemo2026!",
        "role": CommunityRole.VIEWER,
    },
]

DEMO_PROJECTS = [
    {
        "name": "Bug Fixer Web Application",
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


def _is_production_settings() -> bool:
    settings_module = getattr(settings, "SETTINGS_MODULE", "") or ""
    return settings_module.rsplit(".", 1)[-1] == "production"


class Command(BaseCommand):
    help = (
        "Seeds local development demo data: one organization, five demo users "
        "(one per Community role), and three projects. Idempotent — safe to "
        "re-run. Refuses to run under production settings, and refuses to run "
        "if a different organization is already configured (Community allows "
        "only one)."
    )

    def handle(self, *args, **options):
        if _is_production_settings():
            raise CommandError(
                "seed_demo refuses to run with production settings "
                f"(SETTINGS_MODULE={settings.SETTINGS_MODULE!r}). This command creates "
                "well-known, publicly-documented demo accounts and must never touch a "
                "production database."
            )

        organization = self._ensure_organization()

        users = {}
        for persona in PERSONAS:
            users[persona["key"]] = self._ensure_member(organization, persona)

        for spec in DEMO_PROJECTS:
            self._ensure_project(organization, spec, lead=users[spec["lead"]])

        self._report(organization)

    # -- organization -----------------------------------------------------

    def _ensure_organization(self) -> Organization:
        organization = Organization.objects.filter(slug=DEMO_ORG_SLUG).first()
        if organization is not None:
            self.stdout.write(f"Organization '{DEMO_ORG_SLUG}' already exists — reusing it.")
            return organization

        admin_persona = next(p for p in PERSONAS if p["key"] == "admin")
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
            # collided with "Bug Fixer Demo"'s slugified name — don't
            # silently seed data under an unexpected slug.
            raise CommandError(
                f"Created organization slug {organization.slug!r} does not match the "
                f"expected demo slug {DEMO_ORG_SLUG!r}."
            )

        self.stdout.write(f"Created organization '{organization.name}' ({organization.slug}).")
        return organization

    # -- members ------------------------------------------------------------

    def _ensure_member(self, organization: Organization, persona: dict):
        email = persona["email"].lower()

        membership = (
            OrganizationMembership.objects.select_related("user")
            .filter(organization=organization, user__email=email)
            .first()
        )

        if membership is not None:
            self._sync_persona(membership.user, persona)
            if membership.role != persona["role"]:
                membership = change_member_role(membership=membership, new_role=persona["role"])
                self.stdout.write(f"Updated role for {email} -> {persona['role']}.")
            else:
                self.stdout.write(f"Member {email} already up to date.")
            return membership.user

        user = self._invite_and_accept(organization, persona, email)
        self._sync_persona(user, persona)
        self.stdout.write(f"Created member {email} ({persona['role']}).")
        return user

    def _invite_and_accept(self, organization: Organization, persona: dict, email: str):
        # Goes through the same invite -> accept path a real teammate would,
        # so seeding stays on the business-rule-enforced path (role
        # validation, membership creation) rather than constructing
        # memberships directly.
        admin_persona = next(p for p in PERSONAS if p["key"] == "admin")
        invited_by = User.objects.filter(email=admin_persona["email"].lower()).first()

        try:
            _invitation, raw_token = create_invitation(
                organization=organization, invited_by=invited_by, email=email, role=persona["role"]
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
                organization=organization, invited_by=invited_by, email=email, role=persona["role"]
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

    # -- reporting ------------------------------------------------------

    def _report(self, organization: Organization) -> None:
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

        rows = [(p["role"], p["email"], p["password"]) for p in PERSONAS]
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
