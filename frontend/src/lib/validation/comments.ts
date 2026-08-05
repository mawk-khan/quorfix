import { z } from "zod";

// Mirrors apps.comments.models.MAX_COMMENT_BODY_LENGTH and
// apps.comments.services._normalize_body (trim, then require 1-10,000
// chars). This is a UI-responsiveness guard only — the backend remains the
// authoritative validator.
export const MAX_COMMENT_BODY_LENGTH = 10_000;

export const commentBodySchema = z.object({
  body: z
    .string()
    .trim()
    .min(1, "Comment cannot be empty.")
    .max(MAX_COMMENT_BODY_LENGTH, `Comment must be ${MAX_COMMENT_BODY_LENGTH.toLocaleString()} characters or fewer.`),
});

export type CommentBodyFormValues = z.infer<typeof commentBodySchema>;
