import type { CommunityRole, Session } from "@/lib/api/types";

// Must match backend/apps/accounts/services.py's DEMO_ORGANIZATION_SLUG —
// the "Quorfix Demo" organization every demo persona belongs to.
export const DEMO_ORGANIZATION_SLUG = "quorfix-demo";

export const DEMO_ROLES: { value: CommunityRole; label: string }[] = [
  { value: "administrator", label: "Administrator" },
  { value: "developer", label: "Developer" },
  { value: "qa", label: "QA Tester" },
  { value: "reporter", label: "Reporter" },
  { value: "viewer", label: "Viewer" },
];

export function demoRoleLabel(role: CommunityRole): string {
  return DEMO_ROLES.find((r) => r.value === role)?.label ?? role;
}

// Authoritative check for whether the current session belongs to one of the
// five Quorfix Demo personas — derived entirely from the session response's
// own `organization`/`authenticated` fields (apps.organizations.views.
// SessionView), never from anything the client stored itself (e.g.
// localStorage). Callers must additionally check `session.demo_mode` before
// using this to decide whether to show anything: an installation could in
// principle have an organization slugged "quorfix-demo" without demo mode
// being enabled, and that must not be treated as a demo persona.
export function isDemoPersonaSession(session: Session | undefined): boolean {
  return session?.authenticated === true && session.organization?.slug === DEMO_ORGANIZATION_SLUG;
}
