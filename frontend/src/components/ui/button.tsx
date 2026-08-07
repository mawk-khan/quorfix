import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const BASE =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-field font-medium " +
  "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:cursor-not-allowed disabled:opacity-50";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-primary text-white hover:bg-primary-hover",
  secondary: "border border-border bg-surface text-text-primary hover:bg-page",
  ghost: "text-text-primary hover:bg-page",
  danger: "border border-border bg-surface text-danger hover:bg-danger-subtle",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-11 px-5 text-base",
};

/** Returns just the className string, for non-<button> elements that must
 * look like a button (e.g. a Next.js <Link> used as a primary CTA) — keeps
 * every button-shaped element, regardless of tag, visually identical. */
export function buttonVariants(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  className?: string,
): string {
  return cn(BASE, VARIANTS[variant], SIZES[size], className);
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading = false, disabled, icon, className, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={buttonVariants(variant, size, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? (
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      ) : (
        icon
      )}
      {children}
    </button>
  );
});

/** Square icon-only button — same height scale as Button, no text label.
 * Callers must always supply an accessible name via aria-label. */
export const IconButton = forwardRef<HTMLButtonElement, Omit<ButtonProps, "icon" | "loading">>(
  function IconButton({ size = "md", variant = "ghost", className, children, ...props }, ref) {
    const dims: Record<ButtonSize, string> = { sm: "size-8", md: "size-10", lg: "size-11" };
    return (
      <button
        ref={ref}
        className={cn(BASE, VARIANTS[variant], dims[size], "p-0", className)}
        {...props}
      >
        {children}
      </button>
    );
  },
);
