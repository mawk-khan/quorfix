import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";

/** A pulsing placeholder block for loading states. `aria-hidden` since the
 * loading state itself is announced separately (role="status" wrapper at
 * the call site) — this is purely decorative. */
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-field bg-gray-200", className)}
      {...props}
    />
  );
}
