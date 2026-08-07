"use client";

import { UploadCloud } from "lucide-react";
import { useId, useRef, useState } from "react";

import { cn } from "@/lib/cn";
import { ApiError } from "@/lib/api/client";
import {
  ALLOWED_ATTACHMENT_CONTENT_TYPES,
  MAX_ATTACHMENT_SIZE_BYTES,
  attachmentKeys,
  formatFileSize,
  initiateAttachmentUpload,
  uploadAttachmentBytes,
} from "@/lib/api/attachments";
import { activityKeys } from "@/lib/api/bugs";
import type { Attachment } from "@/lib/api/types";
import { useQueryClient } from "@tanstack/react-query";

function describeError(error: unknown): string {
  if (error instanceof ApiError && typeof error.body === "object" && error.body !== null) {
    const body = error.body as Record<string, unknown>;
    if ("detail" in body) return String(body.detail);
    for (const key of Object.keys(body)) {
      const value = body[key];
      if (Array.isArray(value) && value.length > 0) return String(value[0]);
    }
  }
  return "Upload failed.";
}

function validateFile(file: File): string | null {
  if (!ALLOWED_ATTACHMENT_CONTENT_TYPES.has(file.type)) {
    return `"${file.name}" is not an accepted file type.`;
  }
  if (file.size > MAX_ATTACHMENT_SIZE_BYTES) {
    return `"${file.name}" is larger than the 10 MB limit.`;
  }
  return null;
}

interface UploadRow {
  localId: string;
  file: File;
  progress: number;
  status: "uploading" | "success" | "failed";
  error?: string;
  attachmentId?: string;
}

export interface AttachmentUploadProps {
  bugId: string;
  disabled: boolean;
  disabledReason?: string;
  // The currently-persisted, backend-visible attachment ids for this bug
  // (attachment-list.tsx's own query result, threaded down through
  // bug-attachments.tsx). Used only to know when a successful in-flight
  // upload's row can be dropped — once its attachment id actually shows up
  // here, the real row in AttachmentList has taken over, so the temporary
  // one is removed rather than lingering as a duplicate.
  persistedAttachmentIds: Set<string>;
}

export function AttachmentUpload({ bugId, disabled, disabledReason, persistedAttachmentIds }: AttachmentUploadProps) {
  const queryClient = useQueryClient();
  const acceptedTypesId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const nextLocalId = useRef(0);
  const [rows, setRows] = useState<UploadRow[]>([]);
  const [dragOver, setDragOver] = useState(false);

  // Derived at render time rather than synced via an effect: once a
  // successful row's attachment id shows up in the confirmed persisted
  // list, it simply stops being rendered here — no setState-in-effect
  // cascade, and `rows` itself is left untouched (finished rows are cheap
  // to keep around, they just become invisible).
  const visibleRows = rows.filter(
    (row) => !(row.status === "success" && row.attachmentId && persistedAttachmentIds.has(row.attachmentId)),
  );

  function invalidateAfterUpload() {
    queryClient.invalidateQueries({ queryKey: attachmentKeys.lists(bugId) });
    queryClient.invalidateQueries({ queryKey: activityKeys.lists(bugId) });
  }

  function updateRow(localId: string, patch: Partial<UploadRow>) {
    setRows((current) => current.map((row) => (row.localId === localId ? { ...row, ...patch } : row)));
  }

  function removeRow(localId: string) {
    setRows((current) => current.filter((row) => row.localId !== localId));
  }

  async function runUpload(localId: string, file: File) {
    try {
      const { attachment, upload } = await initiateAttachmentUpload(bugId, {
        original_filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
      });
      updateRow(localId, { attachmentId: attachment.id });

      const uploaded: Attachment = await uploadAttachmentBytes(upload.url, file, {
        onProgress: (fraction) => updateRow(localId, { progress: fraction }),
      });

      updateRow(localId, { status: "success", progress: 1, attachmentId: uploaded.id });
      invalidateAfterUpload();
      // The row is removed once attachment-list.tsx's own query confirms
      // the persisted attachment is actually visible (see bug-attachments.
      // tsx, which drops any local row whose attachmentId has appeared in
      // the fetched list) — not immediately here, to avoid a gap where
      // neither the temp row nor the real row is on screen.
    } catch (error) {
      updateRow(localId, { status: "failed", error: describeError(error) });
    }
  }

  function enqueueFiles(fileList: FileList | null) {
    if (!fileList || disabled) return;
    for (const file of Array.from(fileList)) {
      const localId = `upload-${nextLocalId.current++}`;
      const clientError = validateFile(file);
      if (clientError) {
        setRows((current) => [...current, { localId, file, progress: 0, status: "failed", error: clientError }]);
        continue;
      }
      setRows((current) => [...current, { localId, file, progress: 0, status: "uploading" }]);
      void runUpload(localId, file);
    }
  }

  function retryRow(localId: string) {
    const row = rows.find((r) => r.localId === localId);
    if (!row) return;
    // Never reuses the failed row's attachment id or calls upload-bytes
    // again on it — a fresh local row runs the full initiate+upload flow
    // from scratch, matching the backend's one-shot pending -> uploaded/
    // failed lifecycle (a failed attachment row can never be resumed).
    removeRow(localId);
    const freshLocalId = `upload-${nextLocalId.current++}`;
    setRows((current) => [...current, { localId: freshLocalId, file: row.file, progress: 0, status: "uploading" }]);
    void runUpload(freshLocalId, row.file);
  }

  if (disabled) {
    return (
      <p className="text-sm text-text-secondary">
        {disabledReason ?? "Uploads are not available for this bug."}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragOver(false);
          enqueueFiles(event.dataTransfer.files);
        }}
        className={cn(
          "rounded-card border-2 border-dashed p-6 text-center text-sm transition-colors",
          dragOver ? "border-primary bg-primary-subtle" : "border-border-strong",
        )}
      >
        <UploadCloud aria-hidden="true" className="mx-auto size-6 text-text-muted" />
        <p className="mt-2 text-text-secondary">
          Drag and drop a file here, or{" "}
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="font-medium text-primary underline"
          >
            browse
          </button>
        </p>
        <input
          ref={inputRef}
          type="file"
          className="sr-only"
          aria-label="Upload attachment"
          aria-describedby={acceptedTypesId}
          onChange={(event) => {
            enqueueFiles(event.target.files);
            event.target.value = "";
          }}
        />
        <p id={acceptedTypesId} className="mt-2 text-xs text-text-secondary">
          Images, PDF, text/CSV, JSON, ZIP, MP4, Word/Excel. Max 10 MB. SVG is not accepted.
        </p>
      </div>

      {visibleRows.length > 0 && (
        <ul className="space-y-1.5">
          {visibleRows.map((row) => (
            <li
              key={row.localId}
              className="flex items-center gap-2 rounded-field border border-border px-3 py-2 text-sm"
              data-testid="upload-row"
            >
              <span className="flex-1 truncate text-text-primary">{row.file.name}</span>
              <span className="text-xs text-text-secondary">{formatFileSize(row.file.size)}</span>
              {row.status === "uploading" && (
                <span
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(row.progress * 100)}
                  aria-label={`Uploading ${row.file.name}`}
                  className="text-xs text-text-secondary"
                >
                  Uploading… {Math.round(row.progress * 100)}%
                </span>
              )}
              {row.status === "success" && (
                <span role="status" className="text-xs text-success">
                  Uploaded
                </span>
              )}
              {row.status === "failed" && (
                <>
                  <span role="alert" className="text-xs text-danger">
                    {row.error ?? "Upload failed."}
                  </span>
                  <button
                    type="button"
                    onClick={() => retryRow(row.localId)}
                    className="text-xs font-medium text-primary underline"
                  >
                    Retry
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
