"use client";

import { useQueryClient } from "@tanstack/react-query";
import { File, FileImage, FileText, FileVideo } from "lucide-react";
import { useRef, useState } from "react";

import { AlertDialog } from "@/components/alert-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ApiError } from "@/lib/api/client";
import {
  attachmentKeys,
  downloadAttachment,
  formatFileSize,
  removeAttachment,
} from "@/lib/api/attachments";
import { activityKeys } from "@/lib/api/bugs";
import { formatDateTime } from "@/lib/dashboard/format";
import type { Attachment, PaginatedResponse } from "@/lib/api/types";

const SCAN_STATUS_LABELS: Record<Attachment["scan_status"], string> = {
  not_scanned: "Not scanned",
  pending: "Scan pending",
  clean: "Clean",
  infected: "Infected",
};

function actorLabel(user: { first_name: string; last_name: string; email: string }): string {
  const fullName = `${user.first_name} ${user.last_name}`.trim();
  return fullName || user.email;
}

function describeError(error: unknown): string {
  if (error instanceof ApiError && typeof error.body === "object" && error.body !== null) {
    const body = error.body as Record<string, unknown>;
    if ("detail" in body) return String(body.detail);
  }
  return "Something went wrong.";
}

function AttachmentRow({ bugId, attachment }: { bugId: string; attachment: Attachment }) {
  const queryClient = useQueryClient();
  const [confirmingRemove, setConfirmingRemove] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);
  const [pending, setPending] = useState<"download" | "remove" | null>(null);
  // Local, immediate hide — independent of whether a parent's list query
  // happens to be subscribed to the same cache key this patches below. The
  // cache patch keeps every other subscriber (e.g. bug-attachments.tsx's own
  // list query) in sync; this flag is what guarantees *this* row disappears
  // right away regardless of that wiring.
  const [removed, setRemoved] = useState(false);
  const removeButtonRef = useRef<HTMLButtonElement>(null);

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: attachmentKeys.lists(bugId) });
    queryClient.invalidateQueries({ queryKey: activityKeys.lists(bugId) });
  }

  async function handleDownload() {
    setPending("download");
    setRowError(null);
    try {
      await downloadAttachment(bugId, attachment.id, attachment.original_filename);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setRowError("This file is no longer available.");
        invalidate();
      } else {
        setRowError(describeError(error));
      }
    } finally {
      setPending(null);
    }
  }

  async function handleRemove() {
    setPending("remove");
    setRowError(null);
    try {
      await removeAttachment(bugId, attachment.id);
      setConfirmingRemove(false);
      setRemoved(true);
      // Removed immediately from the visible list, not left in place with a
      // placeholder (unlike comments) — the backend's own list selector
      // already excludes removed attachments entirely.
      queryClient.setQueriesData<PaginatedResponse<Attachment>>(
        { queryKey: attachmentKeys.lists(bugId) },
        (old) => (old ? { ...old, results: old.results.filter((a) => a.id !== attachment.id) } : old),
      );
      invalidate();
    } catch (error) {
      setConfirmingRemove(false);
      setRowError(describeError(error));
      invalidate();
    } finally {
      setPending(null);
    }
  }

  if (removed) return null;

  const FileIcon = attachment.content_type.startsWith("image/")
    ? FileImage
    : attachment.content_type.startsWith("video/")
      ? FileVideo
      : attachment.content_type.startsWith("text/") || attachment.content_type === "application/json"
        ? FileText
        : File;

  return (
    <li
      className="flex items-start gap-3 rounded-field border border-border p-3 text-sm"
      data-testid="attachment-row"
    >
      <span
        aria-hidden="true"
        className="flex size-9 flex-none items-center justify-center rounded-field bg-page text-text-secondary"
      >
        <FileIcon className="size-[18px]" />
      </span>

      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-x-2">
          <span className="font-medium text-text-primary">{attachment.original_filename}</span>
          <span className="text-xs text-text-secondary">{formatFileSize(attachment.size_bytes)}</span>
          <span className="text-xs text-text-secondary">{SCAN_STATUS_LABELS[attachment.scan_status]}</span>
        </div>
        <div className="text-xs text-text-secondary">
          Uploaded by {actorLabel(attachment.uploaded_by)}
          {attachment.uploaded_at && ` on ${formatDateTime(attachment.uploaded_at)}`}
        </div>

        {rowError && (
          <p role="alert" className="text-xs text-danger">
            {rowError}
          </p>
        )}

        <div className="flex items-center gap-3 text-xs">
          <button
            type="button"
            onClick={handleDownload}
            disabled={pending === "download"}
            className="font-medium text-primary underline disabled:opacity-50"
          >
            Download
          </button>
          {attachment.can_remove && !confirmingRemove && (
            <button
              ref={removeButtonRef}
              type="button"
              onClick={() => setConfirmingRemove(true)}
              className="font-medium text-danger underline"
            >
              Remove
            </button>
          )}
        </div>

        {confirmingRemove && (
          <AlertDialog
            title="Confirm remove attachment"
            description="Remove this attachment? This cannot be undone."
            confirmLabel="Confirm remove"
            onConfirm={handleRemove}
            onCancel={() => setConfirmingRemove(false)}
            pending={pending === "remove"}
            restoreFocusTo={removeButtonRef}
          />
        )}
      </div>
    </li>
  );
}

export interface AttachmentListProps {
  bugId: string;
  attachments: Attachment[];
}

export function AttachmentList({ bugId, attachments }: AttachmentListProps) {
  if (attachments.length === 0) {
    return <EmptyState icon={File} title="No attachments yet" />;
  }

  return (
    <ul className="space-y-2">
      {attachments.map((attachment) => (
        <AttachmentRow key={attachment.id} bugId={bugId} attachment={attachment} />
      ))}
    </ul>
  );
}
