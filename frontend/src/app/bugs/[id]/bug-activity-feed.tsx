"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { activityKeys, listBugActivity } from "@/lib/api/bugs";

const VERB_LABELS: Record<string, string> = {
  created: "created this bug",
  status_changed: "changed status",
  assigned: "assigned",
  unassigned: "unassigned",
  priority_changed: "changed priority",
  severity_changed: "changed severity",
  field_updated: "updated a field",
  tag_added: "added a tag",
  tag_removed: "removed a tag",
  relationship_added: "added a relationship",
  relationship_removed: "removed a relationship",
  archived: "archived this bug",
  restored: "restored this bug",
  comment_added: "added a comment",
  comment_edited: "edited a comment",
  comment_deleted: "deleted a comment",
  comment_redacted: "redacted a comment",
  mention_created: "mentioned a teammate",
  attachment_added: "added an attachment",
  attachment_removed: "removed an attachment",
};

function actorLabel(actor: { first_name: string; last_name: string; email: string } | null): string {
  if (!actor) return "System";
  const fullName = `${actor.first_name} ${actor.last_name}`.trim();
  return fullName || actor.email;
}

export function BugActivityFeed({ bugId }: { bugId: string }) {
  const [page, setPage] = useState(1);

  const query = useQuery({
    queryKey: activityKeys.list(bugId, page),
    queryFn: () => listBugActivity(bugId, page),
  });

  if (query.isLoading) {
    return <p className="text-sm text-gray-500">Loading activity…</p>;
  }

  if (query.isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Could not load activity.
      </p>
    );
  }

  const activities = query.data?.results ?? [];

  return (
    <div className="space-y-2">
      {activities.length === 0 && <p className="text-sm text-gray-500">No activity yet.</p>}
      <ul className="space-y-2">
        {activities.map((activity) => (
          <li key={activity.id} className="border-t pt-2 text-sm">
            <span className="font-medium">{actorLabel(activity.actor)}</span>{" "}
            {VERB_LABELS[activity.verb] ?? activity.verb}
            {activity.from_value && activity.to_value && (
              <span className="text-gray-600">
                {" "}
                ({activity.from_value} → {activity.to_value})
              </span>
            )}
            {!activity.from_value && activity.to_value && (
              <span className="text-gray-600"> ({activity.to_value})</span>
            )}
            <span className="ml-2 text-xs text-gray-500">
              {new Date(activity.created_at).toLocaleString()}
            </span>
          </li>
        ))}
      </ul>

      {query.data && (query.data.next || page > 1) && (
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
            disabled={!query.data.next}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
