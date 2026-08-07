import Link from "next/link";

export interface AccessStateProps {
  heading: string;
  message: string;
  action?: { href: string; label: string };
}

// Full-body content for a page that can't show its normal content right now
// — sign-in-required, not-found, or forbidden. A heading (so a screen
// reader user navigating by headings immediately learns why the page is
// empty) plus plain text — deliberately not role="alert": these are static,
// page-load-time conditions, not a dynamic interruption of content the user
// is already reading, so an assertive live-region announcement on every
// visit would be spurious noise rather than useful signal.
export function AccessState({ heading, message, action }: AccessStateProps) {
  return (
    <div>
      <h1 className="text-lg font-semibold text-text-primary">{heading}</h1>
      <p className="mt-1 text-sm text-text-secondary">{message}</p>
      {action && (
        <Link href={action.href} className="mt-3 inline-block text-sm font-medium text-primary underline">
          {action.label}
        </Link>
      )}
    </div>
  );
}
