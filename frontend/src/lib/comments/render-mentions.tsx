import type { ReactNode } from "react";

// Mirrors apps.comments.mentions.MENTION_TOKEN_RE exactly: a bounded,
// newline-free display-name segment, and a loose id segment (the real
// validation is the uuid.UUID(...) parse below, same as the backend). Global
// flag so a single body can contain multiple tokens.
const MENTION_TOKEN_RE = /@\[([^[\]\n]{1,100})\]\(mention:([0-9a-fA-F-]{36})\)/g;

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isValidUuid(value: string): boolean {
  return UUID_RE.test(value);
}

// Renders a comment body as safe React text nodes — never
// dangerouslySetInnerHTML. Only segments that are both syntactically valid
// mention tokens AND carry a real UUID render as a styled mention; anything
// else (malformed brackets, a non-UUID id, plain "@name" text) falls through
// to plain text, exactly like the backend's own parser silently ignores
// invalid tokens rather than treating them as an error. This is a display
// convenience only — it never grants or implies mention authorization; only
// apps.comments.mentions.resolve_mentions decides who was actually notified.
export function renderCommentBody(body: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  MENTION_TOKEN_RE.lastIndex = 0;
  while ((match = MENTION_TOKEN_RE.exec(body)) !== null) {
    // The regex has exactly two capture groups, so both are always present
    // on a match — the `?? ""` fallbacks only satisfy noUncheckedIndexedAccess,
    // they are never actually reached.
    const full = match[0];
    const displayName = match[1] ?? "";
    const userId = match[2] ?? "";
    const start = match.index;

    if (start > lastIndex) {
      nodes.push(body.slice(lastIndex, start));
    }

    if (isValidUuid(userId)) {
      nodes.push(
        <span
          key={`mention-${key++}`}
          className="rounded-field bg-primary-subtle px-1 font-medium text-primary"
          data-testid="mention-token"
        >
          @{displayName}
        </span>,
      );
    } else {
      nodes.push(full);
    }

    lastIndex = start + full.length;
  }

  if (lastIndex < body.length) {
    nodes.push(body.slice(lastIndex));
  }

  return nodes;
}
