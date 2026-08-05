"use client";

import Link from "next/link";

import type { Project } from "@/lib/api/types";

interface ProjectTableProps {
  projects: Project[];
  hasActiveFilters: boolean;
}

function leadLabel(lead: Project["lead"]): string {
  if (!lead) return "—";
  const fullName = `${lead.first_name} ${lead.last_name}`.trim();
  return fullName || lead.email;
}

export function ProjectTable({ projects, hasActiveFilters }: ProjectTableProps) {
  if (projects.length === 0) {
    return (
      <p className="text-sm text-gray-500">
        {hasActiveFilters ? "No projects match your search or filters." : "No projects yet."}
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
            Name
          </th>
          <th scope="col" className="pb-2">
            Status
          </th>
          <th scope="col" className="pb-2">
            Lead
          </th>
          <th scope="col" className="pb-2">
            Archived
          </th>
        </tr>
      </thead>
      <tbody>
        {projects.map((project) => (
          <tr key={project.id} className="border-t">
            <td className="py-2 font-mono">{project.key}</td>
            <td className="py-2">
              <Link href={`/projects/${project.id}`} className="underline">
                {project.name}
              </Link>
            </td>
            <td className="py-2">{project.status.replace("_", " ")}</td>
            <td className="py-2">{leadLabel(project.lead)}</td>
            <td className="py-2">{project.archived_at ? "Archived" : "Active"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
