import type { ComponentType, ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface EmptyStateProps {
  icon?: ComponentType<{ className?: string }>;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/** Small icon + short heading + concise copy — deliberately minimal, no
 * illustrations. Used for "no bugs yet", "no notifications", "no results",
 * etc. */
export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center gap-1 px-4 py-10 text-center", className)}>
      {Icon && <Icon className="mb-2 size-8 text-text-muted" />}
      <p className="text-sm font-medium text-text-primary">{title}</p>
      {description && <p className="max-w-sm text-sm text-text-secondary">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
