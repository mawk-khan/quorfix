import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-card border border-border bg-surface shadow-xs", className)}
      {...props}
    />
  );
}

export interface CardHeaderProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}

/** Title + optional muted subtitle + optional right-aligned action (e.g. a
 * range-select on a chart card). Pass `children` instead of title/subtitle
 * for full control. */
export function CardHeader({ title, subtitle, action, className, children, ...props }: CardHeaderProps) {
  return (
    <div
      className={cn("flex items-start justify-between gap-4 border-b border-border p-5", className)}
      {...props}
    >
      {children ?? (
        <div className="min-w-0">
          {title && <h2 className="text-sm font-semibold text-text-primary">{title}</h2>}
          {subtitle && <p className="mt-0.5 text-xs text-text-secondary">{subtitle}</p>}
        </div>
      )}
      {action}
    </div>
  );
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5", className)} {...props} />;
}
