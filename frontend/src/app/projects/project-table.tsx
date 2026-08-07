"use client";

import { FolderKanban } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import type { Project } from "@/lib/api/types";

import { ProjectStatusBadge } from "./project-badges";

interface ProjectTableProps {
  projects: Project[];
  hasActiveFilters: boolean;
}

function leadLabel(lead: Project["lead"]): string {
  if (!lead) return "—";
  const fullName = `${lead.first_name} ${lead.last_name}`.trim();
  return fullName || lead.email;
}

const HEADERS = ["Key", "Name", "Status", "Lead", "Archived"];

export function ProjectTable({ projects, hasActiveFilters }: ProjectTableProps) {
  if (projects.length === 0) {
    return hasActiveFilters ? (
      <EmptyState title="No projects match your search or filters" description="Try adjusting or clearing the filters above." />
    ) : (
      <EmptyState icon={FolderKanban} title="No projects yet" />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Projects</caption>
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
          {projects.map((project) => (
            <tr key={project.id} className="border-b border-border last:border-b-0 hover:bg-page">
              <td className="whitespace-nowrap px-4 py-3 pl-5 font-mono text-xs text-text-secondary">
                {project.key}
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <Link
                  href={`/projects/${project.id}`}
                  className="font-medium text-text-primary underline underline-offset-2 hover:text-primary"
                >
                  {project.name}
                </Link>
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <ProjectStatusBadge status={project.status} />
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-text-primary">{leadLabel(project.lead)}</td>
              <td className="whitespace-nowrap px-4 py-3 pr-5">
                {project.archived_at ? <Badge tone="amber">Archived</Badge> : <Badge tone="green">Active</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
