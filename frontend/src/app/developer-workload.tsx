"use client";

import type { UseQueryResult } from "@tanstack/react-query";

import type { Workload, WorkloadEntry } from "@/lib/api/types";
import { formatCount } from "@/lib/dashboard/format";

import { DashboardSection } from "./dashboard-section";

interface DeveloperWorkloadProps {
  query: Pick<UseQueryResult<Workload>, "data" | "isLoading" | "isError" | "error" | "refetch">;
}

function WorkloadRow({ label, count, badge }: { label: string; count: number; badge?: string }) {
  return (
    <tr className="border-t">
      <td className="py-2 pr-3">
        {label}
        {badge && (
          <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800">
            {badge}
          </span>
        )}
      </td>
      <td className="py-2 text-right tabular-nums">{formatCount(count)}</td>
    </tr>
  );
}

export function DeveloperWorkload({ query }: DeveloperWorkloadProps) {
  return (
    <DashboardSection
      title="Bugs per developer"
      query={query}
      isEmpty={(data) =>
        data.eligible.length === 0 && data.unassigned === 0 && data.needs_reassignment.length === 0
      }
      emptyMessage="No open bugs to assign."
    >
      {(workload) => (
        <>
          <p className="mb-2 text-xs text-gray-500">
            Current open workload — not affected by the date range
          </p>
          <table className="w-full text-sm">
            <caption className="sr-only">Current open bug workload by assignee</caption>
            <thead>
              <tr className="text-left text-xs text-gray-500">
                <th scope="col" className="pb-1 font-medium">
                  Assignee
                </th>
                <th scope="col" className="pb-1 text-right font-medium">
                  Open bugs
                </th>
              </tr>
            </thead>
            <tbody>
              {workload.eligible.map((entry: WorkloadEntry) => (
                <WorkloadRow key={entry.user_id} label={entry.name} count={entry.count} />
              ))}
              {workload.needs_reassignment.map((entry: WorkloadEntry) => (
                <WorkloadRow
                  key={entry.user_id}
                  label={entry.name}
                  count={entry.count}
                  badge="Needs reassignment"
                />
              ))}
              <WorkloadRow label="Unassigned" count={workload.unassigned} />
            </tbody>
          </table>
          {workload.needs_reassignment.length > 0 && (
            <p className="mt-3 text-xs text-gray-500">
              &ldquo;Needs reassignment&rdquo; means the assignee&rsquo;s current role can no longer be
              assigned bugs (they were changed to reporter or viewer, not removed from the
              organization) — distinct from &ldquo;Unassigned&rdquo;, which has no assignee at all.
            </p>
          )}
        </>
      )}
    </DashboardSection>
  );
}
