"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import Link from "next/link";

import type { ActiveProject } from "@/lib/api/types";
import { formatCount, formatStatusLabel } from "@/lib/dashboard/format";

import { DashboardSection } from "./dashboard-section";

interface ActiveProjectsPanelProps {
  query: Pick<UseQueryResult<ActiveProject[]>, "data" | "isLoading" | "isError" | "error" | "refetch">;
}

export function ActiveProjectsPanel({ query }: ActiveProjectsPanelProps) {
  return (
    <DashboardSection
      title="Active projects"
      query={query}
      isEmpty={(data) => data.length === 0}
      emptyMessage="No active projects."
    >
      {(projects) => (
        <ul className="divide-y">
          {projects.map((project) => (
            <li key={project.id} className="flex items-center justify-between py-2 text-sm">
              <div>
                <Link href={`/projects/${project.id}`} className="font-medium underline">
                  {project.key}
                </Link>{" "}
                — {project.name}
                <span className="ml-2 text-xs text-gray-500">{formatStatusLabel(project.status)}</span>
              </div>
              <div className="text-right text-xs text-gray-500">
                <div>{formatCount(project.open_bugs)} open</div>
                <div>{formatCount(project.total_bugs)} total</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </DashboardSection>
  );
}
