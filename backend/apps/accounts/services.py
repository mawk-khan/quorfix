from django.contrib.auth import login

from apps.core.context import bind_actor_context
from apps.organizations.models import OrganizationMembership

# Demo-only "Quick Access" role login (see apps.accounts.views.DemoLoginView).
# A strict, hardcoded allow-list — the ONLY accounts that endpoint can ever
# authenticate as. Deliberately independent of
# apps.core.management.commands.seed_demo's own PERSONAS list (which exists
# to seed data, not to gate a live authentication decision), so a future
# change to seed data can never widen what this endpoint accepts.
DEMO_ORGANIZATION_SLUG = "quorfix-demo"

DEMO_ROLE_TO_EMAIL = {
    "administrator": "admin@quorfix.local",
    "developer": "developer@quorfix.local",
    "qa": "qa@quorfix.local",
    "reporter": "reporter@quorfix.local",
    "viewer": "viewer@quorfix.local",
}


def start_session(request, user, *, backend=None, organization_id=None) -> None:
    """Starts an authenticated session for `user` and binds actor context for
    logging — the "successful authentication" tail shared by every login
    path in this app.

    `backend` must be passed explicitly whenever `user` was resolved by
    something other than `django.contrib.auth.authenticate()` (which stamps
    `user.backend` as a side effect) — AUTHENTICATION_BACKENDS has more than
    one entry, so plain `login(request, user)` would raise otherwise. See
    apps.organizations.views.SetupView/InvitationAcceptView for the same
    requirement.
    """
    if backend is not None:
        login(request, user, backend=backend)
    else:
        login(request, user)
    bind_actor_context(user_id=user.id, organization_id=organization_id)


def resolve_demo_login_user(role: str) -> OrganizationMembership | None:
    """Resolves `role` to the one demo persona it may authenticate as, or
    None if anything about it doesn't check out.

    A single filtered query enforces every requirement at once: the role
    must be in the allow-list, the persona's exact email must belong to an
    active, non-staff, non-superuser account, that account's membership must
    be in the organization slugged "quorfix-demo", and that membership's
    role must match the requested role. Returns None uniformly on any
    mismatch — unknown role, missing/inactive user, staff/superuser account,
    wrong organization, or a stale role — without distinguishing which
    check failed, the same no-account-detail-leakage posture as
    apps.accounts.backends.EmailAuthBackend.
    """
    email = DEMO_ROLE_TO_EMAIL.get(role)
    if email is None:
        return None

    return (
        OrganizationMembership.objects.select_related("user", "organization")
        .filter(
            user__email=email,
            user__is_active=True,
            user__is_staff=False,
            user__is_superuser=False,
            organization__slug=DEMO_ORGANIZATION_SLUG,
            role=role,
        )
        .first()
    )


def is_demo_user(user) -> bool:
    """True iff `user` is one of the five seeded Quorfix Demo personas —
    the same double allow-list check as resolve_demo_login_user (exact
    email AND membership in the org slugged "quorfix-demo"), evaluated
    independently of how the caller authenticated. Unlike
    resolve_demo_login_user, this is NOT gated on settings.QUORFIX_DEMO_MODE
    or on role: it exists purely to protect these five accounts' identity,
    role, and membership from mutation — see
    apps.organizations.services.change_member_role/remove_member/
    create_invitation — regardless of whether Quick Access is currently
    enabled, and regardless of which role the caller is acting as (an
    administrator-role demo persona must not be able to modify itself or
    any other demo persona either).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    email = (user.email or "").lower()
    if email not in DEMO_ROLE_TO_EMAIL.values():
        return False
    return OrganizationMembership.objects.filter(
        user=user, organization__slug=DEMO_ORGANIZATION_SLUG
    ).exists()
