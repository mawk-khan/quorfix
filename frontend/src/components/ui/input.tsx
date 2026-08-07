import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const FIELD_BASE =
  "w-full rounded-field border border-border bg-surface px-3 text-sm text-text-primary " +
  "placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 " +
  "focus-visible:ring-primary focus-visible:border-primary disabled:cursor-not-allowed " +
  "disabled:bg-page disabled:text-text-muted aria-invalid:border-danger aria-invalid:focus-visible:ring-danger";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return <input ref={ref} className={cn(FIELD_BASE, "h-10", className)} {...props} />;
  },
);

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return <textarea ref={ref} className={cn(FIELD_BASE, "min-h-24 py-2", className)} {...props} />;
});
