"use client";

import { useId, useLayoutEffect, useMemo, useRef, useState } from "react";

import { buildMentionToken } from "@/lib/api/comments";
import type { Membership } from "@/lib/api/types";

function memberLabel(member: Membership): string {
  const fullName = `${member.user.first_name} ${member.user.last_name}`.trim();
  return fullName || member.user.email;
}

// Finds the "@query" the caret is currently inside of, if any — scans
// backward from the caret to the nearest "@" that isn't itself preceded by
// a non-whitespace character (so "email@x" never triggers) and isn't
// separated from the caret by whitespace/newline (so a stale "@" earlier in
// the text never re-opens the popover while typing further along).
function findActiveTrigger(
  value: string,
  caret: number,
): { start: number; query: string } | null {
  const upToCaret = value.slice(0, caret);
  const at = upToCaret.lastIndexOf("@");
  if (at === -1) return null;
  const before = upToCaret[at - 1];
  if (before && !/\s/.test(before)) return null;
  const query = upToCaret.slice(at + 1);
  if (/[\s]/.test(query)) return null;
  return { start: at, query };
}

function hasMentionFor(value: string, userId: string): boolean {
  return value.includes(`(mention:${userId})`);
}

export interface MentionTextareaProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  members: Membership[];
  rows?: number;
  placeholder?: string;
  disabled?: boolean;
  "aria-label"?: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
}

// A plain <textarea> plus an "@"-triggered accessible suggestion popover.
// The structured mention token (@[Display Name](mention:<uuid>) — see
// apps.comments.mentions) is inserted directly into the source text and
// stays visible while composing; there is no separate rich-text model.
export function MentionTextarea({
  id,
  value,
  onChange,
  members,
  rows = 4,
  placeholder,
  disabled,
  "aria-label": ariaLabel,
  "aria-invalid": ariaInvalid,
  "aria-describedby": ariaDescribedBy,
}: MentionTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const listboxId = useId();
  const [trigger, setTrigger] = useState<{ start: number; query: string } | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const pendingCursorRef = useRef<number | null>(null);
  const [cursorRequestId, setCursorRequestId] = useState(0);

  // Runs synchronously after the DOM commits the inserted mention text (see
  // insertMention) — in the same React flush as the onChange/setCursorRequestId
  // calls it pairs with, never on a later, unbounded animation frame. A
  // requestAnimationFrame here previously raced with anything the user did
  // before the next paint (most commonly: immediately typing further),
  // since the frame's callback could fire in the middle of that follow-up
  // typing and yank the caret back, scrambling the just-typed characters.
  useLayoutEffect(() => {
    const cursor = pendingCursorRef.current;
    if (cursor === null) return;
    pendingCursorRef.current = null;
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.focus();
      textarea.setSelectionRange(cursor, cursor);
    }
  }, [cursorRequestId]);

  const suggestions = useMemo(() => {
    if (!trigger) return [];
    const query = trigger.query.trim().toLowerCase();
    const matches = query
      ? members.filter((member) => memberLabel(member).toLowerCase().includes(query) || member.user.email.toLowerCase().includes(query))
      : members;
    return matches.slice(0, 8);
  }, [trigger, members]);

  const open = trigger !== null && suggestions.length > 0;

  function syncTriggerFromCaret(nextValue: string, caret: number) {
    const next = findActiveTrigger(nextValue, caret);
    setTrigger(next);
    setActiveIndex(0);
  }

  function handleChange(event: React.ChangeEvent<HTMLTextAreaElement>) {
    const nextValue = event.target.value;
    onChange(nextValue);
    syncTriggerFromCaret(nextValue, event.target.selectionStart ?? nextValue.length);
  }

  function handleSelect(event: React.SyntheticEvent<HTMLTextAreaElement>) {
    const target = event.currentTarget;
    syncTriggerFromCaret(target.value, target.selectionStart ?? target.value.length);
  }

  function insertMention(member: Membership) {
    if (!trigger) return;
    const textarea = textareaRef.current;
    const caret = textarea?.selectionStart ?? trigger.start + trigger.query.length + 1;
    const before = value.slice(0, trigger.start);
    const after = value.slice(caret);

    // Repeated selection of an already-mentioned user is a no-op insertion
    // — just clears the typed "@query" rather than adding a second,
    // confusing duplicate token for the same person.
    const insertion = hasMentionFor(value, member.user.id)
      ? ""
      : `${buildMentionToken(memberLabel(member), member.user.id)} `;

    const nextValue = `${before}${insertion}${after}`;
    onChange(nextValue);
    setTrigger(null);
    pendingCursorRef.current = before.length + insertion.length;
    setCursorRequestId((id) => id + 1);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (!open) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + suggestions.length) % suggestions.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      const selected = suggestions[activeIndex];
      if (selected) insertMention(selected);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setTrigger(null);
    }
  }

  const activeOptionId = open ? `${listboxId}-option-${activeIndex}` : undefined;

  return (
    <div className="relative">
      <textarea
        ref={textareaRef}
        id={id}
        value={value}
        onChange={handleChange}
        onSelect={handleSelect}
        onKeyDown={handleKeyDown}
        onBlur={() => setTrigger(null)}
        rows={rows}
        placeholder={placeholder}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-invalid={ariaInvalid}
        aria-describedby={ariaDescribedBy}
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        aria-activedescendant={activeOptionId}
        role="combobox"
        className="w-full rounded border px-3 py-2"
      />
      {/* Announces the suggestion count as it changes while composing an
          "@" mention — separate from the listbox itself, since a listbox's
          own option count isn't announced by every screen reader on every
          keystroke. Text only changes (so only announces) when the count
          itself changes, not on every re-render. */}
      <p aria-live="polite" className="sr-only">
        {open
          ? `${suggestions.length} mention suggestion${suggestions.length === 1 ? "" : "s"} available.`
          : ""}
      </p>
      {open && (
        <ul
          id={listboxId}
          role="listbox"
          aria-label="Mention suggestions"
          className="absolute z-10 mt-1 max-h-48 w-64 overflow-y-auto rounded border bg-white shadow-lg"
        >
          {suggestions.map((member, index) => (
            <li
              key={member.id}
              id={`${listboxId}-option-${index}`}
              role="option"
              aria-selected={index === activeIndex}
              onMouseDown={(event) => {
                // Prevent the textarea from blurring (which would close the
                // popover) before the click is processed.
                event.preventDefault();
                insertMention(member);
              }}
              onMouseEnter={() => setActiveIndex(index)}
              className={`cursor-pointer px-3 py-1.5 text-sm ${
                index === activeIndex ? "bg-blue-50" : ""
              }`}
            >
              <span className="font-medium">{memberLabel(member)}</span>{" "}
              <span className="text-gray-500">({member.user.email})</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
