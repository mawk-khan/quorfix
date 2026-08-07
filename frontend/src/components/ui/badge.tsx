import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export type BadgeTone =
  | "neutral"
  | "blue"
  | "indigo"
  | "violet"
  | "green"
  | "amber"
  | "orange"
  | "red"
  | "rose"
  | "purple";

// Soft tinted background + colored text + subtle matching border — never a
// saturated solid pill. Every tone keeps its own text label regardless of
// color (see StatusBadge/PriorityBadge/SeverityBadge below): color is a
// secondary, supportive signal here, never the only one.
const TONES: Record<BadgeTone, string> = {
  neutral: "bg-gray-100 text-gray-700 border-gray-200",
  blue: "bg-blue-50 text-blue-700 border-blue-200",
  indigo: "bg-indigo-50 text-indigo-700 border-indigo-200",
  violet: "bg-violet-50 text-violet-700 border-violet-200",
  green: "bg-green-50 text-green-700 border-green-200",
  amber: "bg-amber-50 text-amber-800 border-amber-200",
  orange: "bg-orange-50 text-orange-700 border-orange-200",
  red: "bg-red-50 text-red-700 border-red-200",
  rose: "bg-rose-50 text-rose-700 border-rose-200",
  purple: "bg-purple-50 text-purple-700 border-purple-200",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

export function Badge({ tone = "neutral", className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-field border px-2 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
      {...props}
    />
  );
}
