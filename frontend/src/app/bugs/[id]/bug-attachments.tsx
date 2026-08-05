"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { attachmentKeys, listAttachments } from "@/lib/api/attachments";

import { AttachmentList } from "./attachment-list";
import { AttachmentUpload } from "./attachment-upload";

export interface BugAttachmentsProps {
  bugId: string;
  isArchived: boolean;
  canUpload: boolean;
}

export function BugAttachments({ bugId, isArchived, canUpload }: BugAttachmentsProps) {
  const [page, setPage] = useState(1);

  const attachmentsQuery = useQuery({
    queryKey: attachmentKeys.list(bugId, page),
    queryFn: () => listAttachments(bugId, page),
  });

  const attachments = useMemo(() => attachmentsQuery.data?.results ?? [], [attachmentsQuery.data]);
  const persistedAttachmentIds = useMemo(() => new Set(attachments.map((a) => a.id)), [attachments]);

  if (attachmentsQuery.isLoading) {
    return <p className="text-sm text-gray-500">Loading attachments…</p>;
  }

  if (attachmentsQuery.isError) {
    return (
      <div role="alert" className="space-y-2 text-sm text-red-700">
        <p>Could not load attachments.</p>
        <button type="button" onClick={() => attachmentsQuery.refetch()} className="rounded border px-3 py-1 underline">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {canUpload && (
        <AttachmentUpload
          bugId={bugId}
          disabled={isArchived}
          disabledReason="This bug is archived, so attachments cannot be added."
          persistedAttachmentIds={persistedAttachmentIds}
        />
      )}

      <AttachmentList bugId={bugId} attachments={attachments} />

      {attachmentsQuery.data && (attachmentsQuery.data.next || page > 1) && (
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
            disabled={!attachmentsQuery.data.next}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
