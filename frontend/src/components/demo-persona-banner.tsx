// Shown only when settings.QUORFIX_DEMO_MODE is enabled AND the signed-in
// user is one of the five Quorfix Demo personas (apps.accounts.services.
// resolve_demo_login_user) — see isDemoPersonaSession in @/lib/demo. Role
// text comes from the session response's own `role` field, never anything
// the client stored itself, so it can't be spoofed by localStorage. Distinct
// from the generic, operator-authored DemoBanner (DEMO_BANNER_MESSAGE) —
// this one is about *who you're signed in as* and offers a way to change
// that, not a site-wide notice.
export function DemoPersonaBanner({
  roleLabel,
  onSwitchRole,
}: {
  roleLabel: string;
  onSwitchRole: () => void;
}) {
  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-warning/30 bg-warning-subtle px-4 py-2 text-center text-sm text-warning"
    >
      <span>
        <strong className="font-semibold">Public demo</strong> — you&apos;re exploring Quorfix as{" "}
        {roleLabel}. Demo data is shared between visitors and may be reset periodically.
      </span>
      <button
        type="button"
        onClick={onSwitchRole}
        className="rounded-field border border-warning/40 px-2 py-0.5 text-xs font-medium text-warning transition-colors hover:bg-warning/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warning"
      >
        Switch role
      </button>
    </div>
  );
}
