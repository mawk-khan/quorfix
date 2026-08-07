import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface FormFieldProps {
  /** Must match the wrapped control's `id`. */
  htmlFor: string;
  label: ReactNode;
  required?: boolean;
  /** Supporting text shown under the label, above the control. */
  hint?: ReactNode;
  /** react-hook-form's FieldError (or any truthy value) — renders the
   * message as `role="alert"`, `id={`${htmlFor}-error`}`, matching
   * errorProps()'s aria-describedby wiring. */
  error?: { message?: string } | string | null;
  children: ReactNode;
}

/** Label + control + error/hint chrome — the control itself (Input,
 * Textarea, Select, ...) is passed as children so react-hook-form's
 * register() props and errorProps() can be spread directly onto it, same
 * as before this existed. */
export function FormField({ htmlFor, label, required, hint, error, children }: FormFieldProps) {
  const message = typeof error === "string" ? error : error?.message;
  return (
    <div className="space-y-1.5">
      {/* The required marker is a CSS ::after, not a DOM text node — a
          sibling <span aria-hidden> would still show up in a label's plain
          textContent (which is what Testing Library's getByLabelText
          matches against, unlike Playwright's getByLabel which follows the
          real accessible-name algorithm and does respect aria-hidden), so
          `screen.getByLabelText(/^title$/i)` would break the moment any
          required field rendered one. Generated content sidesteps that
          entirely: it's in neither DOM text nor (by default) the
          accessible name. */}
      <label
        htmlFor={htmlFor}
        className={cn(
          "block text-sm font-medium text-text-primary",
          required && "after:ml-0.5 after:text-danger after:content-['*']",
        )}
      >
        {label}
      </label>
      {hint && <p className="text-xs text-text-secondary">{hint}</p>}
      {children}
      {message && (
        <p id={`${htmlFor}-error`} role="alert" className="text-xs text-danger">
          {message}
        </p>
      )}
    </div>
  );
}
