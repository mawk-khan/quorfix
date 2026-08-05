"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";

import { ApiError } from "@/lib/api/client";
import { commentKeys, createComment, listComments } from "@/lib/api/comments";
import { activityKeys } from "@/lib/api/bugs";
import { listMembers } from "@/lib/api/members";
import type { Comment, PaginatedResponse } from "@/lib/api/types";
import { commentBodySchema, type CommentBodyFormValues } from "@/lib/validation/comments";

import { CommentItem } from "./comment-item";
import { MentionTextarea } from "./mention-textarea";

// A large-but-bounded single page (the backend's own max_page_size) rather
// than the UI's default 25 — Community's realistic team sizes fit
// comfortably here, so the mention picker can filter client-side over the
// whole team. See frontend/src/lib/api/members.ts.
const MENTION_MEMBER_PAGE_SIZE = 100;

function describeError(error: unknown): string {
  if (error instanceof ApiError && typeof error.body === "object" && error.body !== null) {
    const body = error.body as Record<string, unknown>;
    if ("detail" in body) return String(body.detail);
    for (const key of Object.keys(body)) {
      const value = body[key];
      if (Array.isArray(value) && value.length > 0) return String(value[0]);
    }
  }
  return "Something went wrong.";
}

export interface BugDiscussionProps {
  bugId: string;
  isArchived: boolean;
  canComment: boolean;
}

export function BugDiscussion({ bugId, isArchived, canComment }: BugDiscussionProps) {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [createError, setCreateError] = useState<string | null>(null);

  const commentsQuery = useQuery({
    queryKey: commentKeys.list(bugId, page),
    queryFn: () => listComments(bugId, page),
  });

  const membersQuery = useQuery({
    queryKey: ["members", "mention-suggestions"],
    queryFn: () => listMembers({ page_size: MENTION_MEMBER_PAGE_SIZE }),
    enabled: canComment,
  });

  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CommentBodyFormValues>({
    resolver: zodResolver(commentBodySchema),
    defaultValues: { body: "" },
  });

  // Any successful mutation on an existing comment (edit/delete/redact)
  // patches every cached comments page for this bug in place with the
  // server's authoritative response — the deleted/redacted placeholder (or
  // edited body) replaces the stale cached body immediately, without
  // waiting on a refetch round-trip.
  function patchComment(updated: Comment) {
    queryClient.setQueriesData<PaginatedResponse<Comment>>(
      { queryKey: commentKeys.lists(bugId) },
      (old) => (old ? { ...old, results: old.results.map((c) => (c.id === updated.id ? updated : c)) } : old),
    );
    queryClient.invalidateQueries({ queryKey: activityKeys.lists(bugId) });
  }

  // A failed edit/delete/redact (403/409) has no fresh Comment to patch the
  // cache with, but the cached can_edit/can_delete/can_redact/status hints
  // may now be stale — refetching is what clears a now-wrong control
  // instead of leaving it clickable.
  function refreshStaleComment() {
    queryClient.invalidateQueries({ queryKey: commentKeys.lists(bugId) });
  }

  const createMutation = useMutation({
    mutationFn: (values: CommentBodyFormValues) => createComment(bugId, values.body),
    onSuccess: () => {
      setCreateError(null);
      reset({ body: "" });
      // Refreshes every cached page for this bug rather than just the
      // current one — a new comment is appended at the end (oldest-first
      // ordering), so it may land on a later page than the one currently
      // being viewed. Comment creation is never something the acting user
      // needs their own notification queries invalidated for (they are the
      // actor, not a recipient), so notification caches are deliberately
      // left untouched here.
      queryClient.invalidateQueries({ queryKey: commentKeys.lists(bugId) });
      queryClient.invalidateQueries({ queryKey: activityKeys.lists(bugId) });
    },
    onError: (error) => {
      // Draft text is preserved automatically — react-hook-form's state is
      // untouched on error, only reset() on success clears it.
      setCreateError(describeError(error));
    },
  });

  const bodyValue = useWatch({ control, name: "body" });

  if (commentsQuery.isLoading) {
    return <p className="text-sm text-gray-500">Loading discussion…</p>;
  }

  if (commentsQuery.isError) {
    return (
      <div role="alert" className="space-y-2 text-sm text-red-700">
        <p>Could not load the discussion.</p>
        <button type="button" onClick={() => commentsQuery.refetch()} className="rounded border px-3 py-1 underline">
          Retry
        </button>
      </div>
    );
  }

  const comments = commentsQuery.data?.results ?? [];
  const members = membersQuery.data ?? [];

  return (
    <div className="space-y-4">
      {comments.length === 0 && <p className="text-sm text-gray-500">No comments yet.</p>}

      <ul className="space-y-3">
        {comments.map((comment) => (
          <CommentItem
            key={comment.id}
            bugId={bugId}
            comment={comment}
            members={members}
            onMutated={patchComment}
            onStaleState={refreshStaleComment}
          />
        ))}
      </ul>

      {commentsQuery.data && (commentsQuery.data.next || page > 1) && (
        <div className="flex items-center justify-between text-sm">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Previous
          </button>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={!commentsQuery.data.next}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}

      {isArchived ? (
        <p className="border-t pt-3 text-sm text-gray-500">
          This bug is archived, so new comments cannot be added. Existing comments remain visible.
        </p>
      ) : canComment ? (
        <form
          onSubmit={handleSubmit((values) => createMutation.mutate(values))}
          className="space-y-2 border-t pt-3"
          aria-label="Add comment"
        >
          <label htmlFor="new-comment-body" className="block text-sm font-medium">
            Add a comment
          </label>
          <Controller
            name="body"
            control={control}
            render={({ field }) => (
              <MentionTextarea
                id="new-comment-body"
                value={field.value}
                onChange={field.onChange}
                members={members}
                rows={3}
                placeholder="Write a comment… use @ to mention a teammate"
                aria-invalid={!!errors.body}
                aria-describedby={errors.body ? "new-comment-body-error" : undefined}
              />
            )}
          />
          <div className="flex items-center justify-between text-xs text-gray-500">
            <span>{bodyValue?.length ?? 0} / 10,000</span>
          </div>
          {errors.body && (
            <p id="new-comment-body-error" role="alert" className="text-sm text-red-700">
              {errors.body.message}
            </p>
          )}
          {createError && (
            <p role="alert" className="text-sm text-red-700">
              {createError}
            </p>
          )}
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="rounded bg-black px-3 py-2 text-sm text-white disabled:opacity-50"
          >
            Post comment
          </button>
        </form>
      ) : (
        <p className="border-t pt-3 text-sm text-gray-500">Viewers can read the discussion but cannot comment.</p>
      )}
    </div>
  );
}
