"use client";

import { useEffect, useId, useRef } from "react";

export interface AlertDialogProps {
  // The dialog's accessible name (aria-labelledby target). Visually hidden
  // for the "boxed" variant, where the description text already carries the
  // same information on screen — repeating it visibly would be redundant.
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  pending?: boolean;
  // "boxed": a bordered red panel (comment/attachment row actions).
  // "inline": a plain text row (section-level archive actions).
  // Same ARIA behavior either way — this only changes visual density to
  // match where each call site already sits in the page.
  variant?: "boxed" | "inline";
  // The element focus should return to when this dialog closes — a ref to
  // the button that triggered it, captured by the *caller*. This can't be
  // read from document.activeElement inside this component's own mount
  // effect: every real call site renders the trigger button and this
  // dialog as mutually exclusive siblings (`{!confirming && <button/>}` /
  // `{confirming && <AlertDialog/>}`), so the trigger has already unmounted
  // — and document.activeElement has already reverted to <body> — by the
  // time this component's effects run.
  restoreFocusTo?: React.RefObject<HTMLElement | null>;
}

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// A small, non-overlay confirmation dialog for destructive actions
// (delete/redact/remove/archive). Mount this only while the confirmation is
// active — conditional rendering (rather than a hidden prop) is what keeps
// it out of the accessibility tree and Tab order the instant it's
// dismissed, and is what the focus-restoration effect below relies on.
//
// Deliberately not a native <dialog>/showModal(): jsdom (this project's
// Vitest environment) does not implement showModal/close, which would make
// this untestable in component tests. A manual focus trap gives the same
// guarantees (initial focus, Tab trap, Escape, focus restoration) with full
// control over exactly which control gets initial focus.
export function AlertDialog({
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  pending = false,
  variant = "boxed",
  restoreFocusTo,
}: AlertDialogProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  // Cancel — never the destructive Confirm button — gets initial focus, so
  // a stray Enter/Space on open can't fire the destructive action. On
  // unmount, focus returns to the caller-supplied trigger element (see
  // restoreFocusTo's own doc comment for why this can't self-capture
  // document.activeElement instead), falling back to document.body only if
  // the caller didn't pass one or it's since been removed from the DOM.
  useEffect(() => {
    cancelButtonRef.current?.focus();
    return () => {
      // Deliberately read lazily, here in the cleanup, not captured eagerly
      // above: the trigger button unmounts in the very same commit that
      // mounts this dialog, so restoreFocusTo.current is already null by
      // the time this effect's own body runs — capturing it there would
      // capture null. It only becomes readable again — pointing at the
      // *new* trigger button React remounts once this dialog itself
      // unmounts — by the time this cleanup actually runs.
      // eslint-disable-next-line react-hooks/exhaustive-deps -- reading restoreFocusTo.current lazily, right here, is required for correctness; eagerly capturing it (the rule's usual suggested fix) always captures null, per the comment above.
      restoreFocusTo?.current?.focus?.();
    };
    // restoreFocusTo itself (the ref object, not .current) has stable
    // identity across re-renders per React's useRef guarantee, so including
    // it changes nothing in practice — added only to satisfy exhaustive-deps.
  }, [restoreFocusTo]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (pending) return; // never disappear out from under an in-flight request
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key !== "Tab") return;

      const container = containerRef.current;
      if (!container) return;
      const focusable = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    // Capture phase: this dialog's Tab trap must win even though it isn't a
    // real focus boundary (no backdrop), before the event reaches whatever
    // element it would otherwise focus next.
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [onCancel, pending]);

  const containerClassName =
    variant === "boxed"
      ? "mt-2 space-y-2 rounded border border-red-300 bg-red-50 p-2 text-xs"
      : "flex items-center gap-3 text-sm";

  return (
    <div
      ref={containerRef}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      className={containerClassName}
    >
      <p id={titleId} className="sr-only">
        {title}
      </p>
      {variant === "boxed" ? (
        <p id={descriptionId}>{description}</p>
      ) : (
        <span id={descriptionId}>{description}</span>
      )}
      <div className="flex items-center gap-2">
        <button
          ref={cancelButtonRef}
          type="button"
          onClick={onCancel}
          disabled={pending}
          className={variant === "boxed" ? "underline disabled:opacity-50" : "underline disabled:opacity-50"}
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={pending}
          className="text-red-700 underline disabled:opacity-50"
        >
          {confirmLabel}
        </button>
      </div>
    </div>
  );
}
