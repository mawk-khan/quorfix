import { Search } from "lucide-react";
import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export const SearchInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function SearchInput({ className, ...props }, ref) {
    return (
      <div className="relative">
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-muted"
        />
        <input
          ref={ref}
          type="search"
          className={cn(
            "h-10 w-full rounded-field border border-border bg-surface pl-9 pr-3 text-sm " +
              "text-text-primary placeholder:text-text-muted focus-visible:outline-none " +
              "focus-visible:ring-2 focus-visible:ring-primary focus-visible:border-primary",
            className,
          )}
          {...props}
        />
      </div>
    );
  },
);
