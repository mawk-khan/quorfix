import { ChevronDown } from "lucide-react";
import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...props }, ref) {
    return (
      <div className="relative">
        <select
          ref={ref}
          className={cn(
            "h-10 w-full appearance-none rounded-field border border-border bg-surface pl-3 pr-9 " +
              "text-sm text-text-primary focus-visible:outline-none focus-visible:ring-2 " +
              "focus-visible:ring-primary focus-visible:border-primary disabled:cursor-not-allowed " +
              "disabled:bg-page disabled:text-text-muted aria-invalid:border-danger " +
              "aria-invalid:focus-visible:ring-danger",
            className,
          )}
          {...props}
        >
          {children}
        </select>
        <ChevronDown
          aria-hidden="true"
          className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-text-secondary"
        />
      </div>
    );
  },
);
