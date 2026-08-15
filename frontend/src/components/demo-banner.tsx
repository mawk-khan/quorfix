// Optional site-wide notice, sourced from the session response's
// `demo_banner` field (empty string on a normal/private installation —
// see DEMO_BANNER_MESSAGE in config/settings/base.py). Rendered as plain
// text only, never HTML, since the value is operator-configured but this
// component has no way to know it was written safely.
//
// Not role="alert": this is a static, page-load-time notice rather than a
// dynamic interruption of content the user is already reading — same
// reasoning as AccessState's own heading/message, see that component.
export function DemoBanner({ message }: { message: string }) {
  return (
    <div
      role="status"
      className="border-b border-warning/30 bg-warning-subtle px-4 py-2 text-center text-sm text-warning"
    >
      {message}
    </div>
  );
}
