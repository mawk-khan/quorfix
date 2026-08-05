"use client";

import { useState } from "react";

import { deleteComment, redactComment, updateComment } from "@/lib/api/comments";
import { ApiError } from "@/lib/api/client";
import type { Comment, Membership } from "@/lib/api/types";
import { renderCommentBody } from "@/lib/comments/render-mentions";
import { MAX_COMMENT_BODY_LENGTH } from "@/lib/validation/comments";

import { MentionTextarea } from "./mention-textarea";

function actorLabel(user: { first_name: string; last_name: string; email: string }): string {
  const fullName = `${user.first_name} ${user.last_name}`.trim();
  return fullName || user.email;
}

function initials(user: { first_name: string; last_name: string; email: string }): string {
  const first = user.first_name.trim()[0];
  const last = user.last_name.trim()[0];
  if (first || last) return `${first ?? ""}${last ?? ""}`.toUpperCase();
  return user.email[0]?.toUpperCase() ?? "?";
}

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

export interface CommentItemProps {
  bugId: string;
  comment: Comment;
  members: Membership[];
  onMutated: (updated: Comment) => void;
  // Invalidates (rather than patches) the comments list — used on a failed
  // mutation, where there is no fresh Comment to patch the cache with but
  // the cached can_edit/can_delete/can_redact/status hints may now be
  // stale (edit window expired, or someone else deleted/redacted/edited
  // the same comment concurrently). Refetching is what actually clears a
  // now-wrong "Edit" button rather than leaving it clickable forever.
  onStaleState: () => void;
}

export function CommentItem({ bugId, comment, members, onMutated, onStaleState }: CommentItemProps) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(comment.body);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [confirmingRedact, setConfirmingRedact] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<"edit" | "delete" | "redact" | null>(null);

  function startEditing() {
    setEditValue(comment.body);
    setActionError(null);
    setEditing(true);
  }

  function cancelEditing() {
    // Preserves the original value — editValue is discarded, comment.body
    // (the last-known-good server value) is untouched either way.
    setEditing(false);
    setActionError(null);
  }

  async function submitEdit() {
    const trimmed = editValue.trim();
    if (!trimmed || trimmed.length > MAX_COMMENT_BODY_LENGTH) return;

    setPendingAction("edit");
    setActionError(null);
    try {
      const updated = await updateComment(bugId, comment.id, trimmed);
      setEditing(false);
      onMutated(updated);
    } catch (error) {
      // Covers the edit window expiring (or the comment being
      // deleted/redacted by someone else) between when this button
      // rendered and when the submit actually reached the server — the
      // backend's 403/409 message is shown verbatim, and the list is
      // refreshed by the caller via onMutated-style invalidation so the
      // stale can_edit hint never lingers.
      if (error instanceof ApiError && (error.status === 403 || error.status === 409)) {
        setEditing(false);
        setActionError(describeError(error));
        onStaleState();
      } else {
        setActionError(describeError(error));
      }
    } finally {
      setPendingAction(null);
    }
  }

  async function confirmDelete() {
    setPendingAction("delete");
    setActionError(null);
    try {
      const updated = await deleteComment(bugId, comment.id);
      setConfirmingDelete(false);
      onMutated(updated);
    } catch (error) {
      setConfirmingDelete(false);
      setActionError(describeError(error));
      onStaleState();
    } finally {
      setPendingAction(null);
    }
  }

  async function confirmRedact() {
    setPendingAction("redact");
    setActionError(null);
    try {
      const updated = await redactComment(bugId, comment.id);
      setConfirmingRedact(false);
      onMutated(updated);
    } catch (error) {
      setConfirmingRedact(false);
      setActionError(describeError(error));
      onStaleState();
    } finally {
      setPendingAction(null);
    }
  }

  const isRemoved = comment.status !== "active";

  return (
    <li className="border-t pt-3" data-testid="comment-item">
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-gray-200 text-xs font-semibold text-gray-700"
        >
          {initials(comment.author)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="font-medium">{actorLabel(comment.author)}</span>
            <span className="text-xs text-gray-500">{new Date(comment.created_at).toLocaleString()}</span>
            {comment.edited_at && !isRemoved && <span className="text-xs text-gray-500">(edited)</span>}
          </div>

          {actionError && (
            <p role="alert" className="mt-1 text-sm text-red-700">
              {actionError}
            </p>
          )}

          {isRemoved ? (
            <p className="mt-1 text-sm italic text-gray-500" data-testid="comment-placeholder">
              {comment.status === "deleted"
                ? "This comment was deleted."
                : "This comment was redacted by an administrator."}
            </p>
          ) : editing ? (
            <div className="mt-1 space-y-2">
              <MentionTextarea
                id={`edit-comment-${comment.id}`}
                value={editValue}
                onChange={setEditValue}
                members={members}
                rows={3}
                aria-label="Edit comment"
              />
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={submitEdit}
                  disabled={pendingAction === "edit" || !editValue.trim()}
                  className="rounded bg-black px-3 py-1 text-sm text-white disabled:opacity-50"
                >
                  Save
                </button>
                <button type="button" onClick={cancelEditing} className="text-sm underline">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <p className="mt-1 whitespace-pre-wrap text-sm">{renderCommentBody(comment.body)}</p>
          )}

          {!isRemoved && !editing && (comment.can_edit || comment.can_delete || comment.can_redact) && (
            <div className="mt-1 flex items-center gap-3 text-xs">
              {comment.can_edit && (
                <button type="button" onClick={startEditing} className="text-blue-700 underline">
                  Edit
                </button>
              )}
              {comment.can_delete && !confirmingDelete && (
                <button type="button" onClick={() => setConfirmingDelete(true)} className="text-red-700 underline">
                  Delete
                </button>
              )}
              {comment.can_redact && !confirmingRedact && (
                <button type="button" onClick={() => setConfirmingRedact(true)} className="text-red-700 underline">
                  Redact
                </button>
              )}
            </div>
          )}

          {confirmingDelete && (
            <div role="alertdialog" aria-label="Confirm delete comment" className="mt-2 space-y-1 rounded border border-red-300 bg-red-50 p-2 text-xs">
              <p>Delete this comment? This cannot be undone.</p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={confirmDelete}
                  disabled={pendingAction === "delete"}
                  className="text-red-700 underline disabled:opacity-50"
                >
                  Confirm delete
                </button>
                <button type="button" onClick={() => setConfirmingDelete(false)} className="underline">
                  Cancel
                </button>
              </div>
            </div>
          )}

          {confirmingRedact && (
            <div role="alertdialog" aria-label="Confirm redact comment" className="mt-2 space-y-1 rounded border border-red-300 bg-red-50 p-2 text-xs">
              <p>
                Redact this comment? The comment body will be permanently removed, but a
                moderation record will remain in the activity history. This cannot be undone.
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={confirmRedact}
                  disabled={pendingAction === "redact"}
                  className="text-red-700 underline disabled:opacity-50"
                >
                  Confirm redact
                </button>
                <button type="button" onClick={() => setConfirmingRedact(false)} className="underline">
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}
