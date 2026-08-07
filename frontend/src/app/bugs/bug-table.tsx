"use client";

import { Bug, SearchX } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
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

const HEADERS = ["Key", "Title", "Status", "Priority", "Severity", "Assignee", "Due"];

export function BugTable({ bugs, hasActiveFilters }: BugTableProps) {
  if (bugs.length === 0) {
    return hasActiveFilters ? (
      <EmptyState
        icon={SearchX}
        title="No bugs match your search or filters"
        description="Try adjusting or clearing the filters above."
      />
    ) : (
      <EmptyState icon={Bug} title="No bugs yet" description="Bugs created in this project will show up here." />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Bugs</caption>
        <thead>
          <tr className="border-b border-border">
            {HEADERS.map((header) => (
              <th
                key={header}
                scope="col"
                className="whitespace-nowrap px-4 py-2.5 text-xs font-medium text-text-secondary first:pl-5 last:pr-5"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {bugs.map((bug) => (
            <tr key={bug.id} className="border-b border-border last:border-b-0 hover:bg-page">
              <td className="whitespace-nowrap px-4 py-3 pl-5 font-mono text-xs text-text-secondary">
                {bug.key}
              </td>
              <td className="px-4 py-3">
                <Link
                  href={`/bugs/${bug.id}`}
                  className="font-medium text-text-primary underline underline-offset-2 hover:text-primary"
                >
                  {bug.title}
                </Link>
                {bug.archived_at && (
                  <Badge tone="amber" className="ml-2">
                    Archived
                  </Badge>
                )}
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <StatusBadge status={bug.status} />
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <PriorityBadge priority={bug.priority} />
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <SeverityBadge severity={bug.severity} />
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-text-primary">{userLabel(bug.assignee)}</td>
              <td className="whitespace-nowrap px-4 py-3 pr-5 text-text-secondary">{bug.due_date ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
