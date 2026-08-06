"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import Link from "next/link";

import type { DashboardActivity, PaginatedResponse } from "@/lib/api/types";
import { actorLabel, VERB_LABELS } from "@/lib/activity/format";
import { formatDateTime } from "@/lib/dashboard/format";

import { DashboardSection } from "./dashboard-section";

interface RecentActivityFeedProps {
  query: Pick<
    UseQueryResult<PaginatedResponse<DashboardActivity>>,
    "data" | "isLoading" | "isError" | "error" | "refetch"
  >;
}

export function RecentActivityFeed({ query }: RecentActivityFeedProps) {
  return (
    <DashboardSection
      title="Recent activity"
      query={query}
      isEmpty={(data) => data.results.length === 0}
      emptyMessage="No recent activity."
    >
      {(page) => (
        <>
          <p className="mb-2 text-xs text-gray-500">Most recent first — not affected by the date range</p>
          <ul className="divide-y">
            {page.results.map((activity) => (
              <li key={activity.id} className="py-2 text-sm">
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
                <div className="mt-0.5 text-xs text-gray-500">
                  <Link href={`/bugs/${activity.bug.id}`} className="underline">
                    {activity.bug.key}
                  </Link>{" "}
                  — {activity.bug.title} ({activity.project.key})
                  <span className="ml-2">{formatDateTime(activity.created_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </DashboardSection>
  );
}
