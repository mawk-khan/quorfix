"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { activityKeys, listBugActivity } from "@/lib/api/bugs";
import { actorLabel, VERB_LABELS } from "@/lib/activity/format";
import { formatDateTime } from "@/lib/dashboard/format";

export function BugActivityFeed({ bugId }: { bugId: string }) {
  const [page, setPage] = useState(1);

  const query = useQuery({
    queryKey: activityKeys.list(bugId, page),
    queryFn: () => listBugActivity(bugId, page),
  });

  if (query.isLoading) {
    return <p className="text-sm text-text-secondary">Loading activity…</p>;
  }

  if (query.isError) {
    return (
      <p role="alert" className="text-sm text-danger">
        Could not load activity.
      </p>
    );
  }

  const activities = query.data?.results ?? [];

  return (
    <div className="space-y-3">
      {activities.length === 0 && <p className="text-sm text-text-secondary">No activity yet.</p>}
      <ul className="divide-y divide-border">
        {activities.map((activity) => (
          <li key={activity.id} className="py-2 text-sm text-text-primary first:pt-0">
            <span className="font-medium">{actorLabel(activity.actor)}</span>{" "}
            {VERB_LABELS[activity.verb] ?? activity.verb}
            {activity.from_value && activity.to_value && (
              <span className="text-text-secondary">
                {" "}
                ({activity.from_value} → {activity.to_value})
              </span>
            )}
            {!activity.from_value && activity.to_value && (
              <span className="text-text-secondary"> ({activity.to_value})</span>
            )}
            <div className="mt-0.5 text-xs text-text-secondary">{formatDateTime(activity.created_at)}</div>
          </li>
        ))}
      </ul>

      {query.data && (query.data.next || page > 1) && (
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
            disabled={!query.data.next}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
