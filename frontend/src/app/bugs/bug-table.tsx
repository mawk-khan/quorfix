"use client";

import Link from "next/link";

import type { BugSummary, User } from "@/lib/api/types";

import { PriorityBadge, SeverityBadge, StatusBadge } from "./bug-badges";

interface BugTableProps {
  bugs: BugSummary[];
  hasActiveFilters: boolean;
}

function userLabel(user: User | null): string {
  if (!user) return "—";
  const fullName = `${user.first_name} ${user.last_name}`.trim();
  return fullName || user.email;
}

export function BugTable({ bugs, hasActiveFilters }: BugTableProps) {
  if (bugs.length === 0) {
    return (
      <p className="text-sm text-gray-500">
        {hasActiveFilters ? "No bugs match your search or filters." : "No bugs yet."}
      </p>
    );
  }

  return (
    <table className="mt-2 w-full text-left text-sm">
      <thead>
        <tr>
          <th scope="col" className="pb-2">
            Key
          </th>
          <th scope="col" className="pb-2">
            Title
          </th>
          <th scope="col" className="pb-2">
            Status
          </th>
          <th scope="col" className="pb-2">
            Priority
          </th>
          <th scope="col" className="pb-2">
            Severity
          </th>
          <th scope="col" className="pb-2">
            Assignee
          </th>
          <th scope="col" className="pb-2">
            Due
          </th>
        </tr>
      </thead>
      <tbody>
        {bugs.map((bug) => (
          <tr key={bug.id} className="border-t">
            <td className="py-2 font-mono">{bug.key}</td>
            <td className="py-2">
              <Link href={`/bugs/${bug.id}`} className="underline">
                {bug.title}
              </Link>
              {bug.archived_at && <span className="ml-2 text-xs text-amber-700">Archived</span>}
            </td>
            <td className="py-2">
              <StatusBadge status={bug.status} />
            </td>
            <td className="py-2">
              <PriorityBadge priority={bug.priority} />
            </td>
            <td className="py-2">
              <SeverityBadge severity={bug.severity} />
            </td>
            <td className="py-2">{userLabel(bug.assignee)}</td>
            <td className="py-2">{bug.due_date ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
