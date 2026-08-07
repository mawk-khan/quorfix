"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
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
    return <p className="text-sm text-text-secondary">Loading attachments…</p>;
  }

  if (attachmentsQuery.isError) {
    return (
      <div role="alert" className="space-y-2 text-sm text-danger">
        <p>Could not load attachments.</p>
        <Button type="button" variant="secondary" size="sm" onClick={() => attachmentsQuery.refetch()}>
          Retry
        </Button>
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
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
          >
            Previous
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setPage((p) => p + 1)}
            disabled={!attachmentsQuery.data.next}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
