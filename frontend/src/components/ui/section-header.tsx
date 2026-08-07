import type { ReactNode } from "react";

/** A smaller heading for a section within a page (e.g. "Attachments",
 * "Discussion" on the bug-detail page) — distinct from PageHeader's <h1>. */
export function SectionHeader({
  title,
  action,
  as: Heading = "h2",
}: {
  title: ReactNode;
  action?: ReactNode;
  as?: "h2" | "h3";
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <Heading className="text-sm font-semibold text-text-primary">{title}</Heading>
      {action}
    </div>
  );
}
