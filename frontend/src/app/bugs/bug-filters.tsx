"use client";

import type { Project } from "@/lib/api/types";
import { BUG_PRIORITIES, BUG_SEVERITIES } from "@/lib/validation/bugs";

const BUG_STATUSES = [
  "new",
  "triaged",
  "assigned",
  "in_progress",
  "ready_for_qa",
  "resolved",
  "reopened",
  "closed",
  "blocked",
  "duplicate",
  "cannot_reproduce",
  "wont_fix",
  "deferred",
] as const;

const SORT_OPTIONS = [
  { value: "-created_at", label: "Newest first" },
  { value: "created_at", label: "Oldest first" },
  { value: "-updated_at", label: "Recently updated" },
  { value: "-priority", label: "Priority (high to low)" },
  { value: "-severity", label: "Severity (high to low)" },
  { value: "due_date", label: "Due date (soonest first)" },
  { value: "-number", label: "Number (newest)" },
] as const;

export interface BugFiltersValue {
  search: string;
  status: string[];
  priority: string;
  severity: string;
  project: string;
  archived: "true" | "false" | "all";
  unassigned: boolean;
  ordering: string;
}

interface BugFiltersProps {
  value: BugFiltersValue;
  projects: Project[];
  onChange: (next: Partial<BugFiltersValue>) => void;
}

export function BugFilters({ value, projects, onChange }: BugFiltersProps) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <label htmlFor="bug-search" className="block text-sm font-medium">
          Search
        </label>
        <input
          id="bug-search"
          type="search"
          value={value.search}
          onChange={(event) => onChange({ search: event.target.value })}
          placeholder="Key or title"
          className="mt-1 rounded border px-3 py-2"
        />
      </div>

      <div>
        <label htmlFor="bug-project-filter" className="block text-sm font-medium">
          Project
        </label>
        <select
          id="bug-project-filter"
          value={value.project}
          onChange={(event) => onChange({ project: event.target.value })}
          className="mt-1 rounded border px-2 py-2"
        >
          <option value="">All projects</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.key}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="bug-status-filter" className="block text-sm font-medium">
          Status
        </label>
        <select
          id="bug-status-filter"
          multiple
          size={4}
          value={value.status}
          onChange={(event) =>
            onChange({ status: Array.from(event.target.selectedOptions, (o) => o.value) })
          }
          className="mt-1 rounded border px-2 py-2"
        >
          {BUG_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="bug-priority-filter" className="block text-sm font-medium">
          Priority
        </label>
        <select
          id="bug-priority-filter"
          value={value.priority}
          onChange={(event) => onChange({ priority: event.target.value })}
          className="mt-1 rounded border px-2 py-2"
        >
          <option value="">Any</option>
          {BUG_PRIORITIES.map((priority) => (
            <option key={priority} value={priority}>
              {priority}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="bug-severity-filter" className="block text-sm font-medium">
          Severity
        </label>
        <select
          id="bug-severity-filter"
          value={value.severity}
          onChange={(event) => onChange({ severity: event.target.value })}
          className="mt-1 rounded border px-2 py-2"
        >
          <option value="">Any</option>
          {BUG_SEVERITIES.map((severity) => (
            <option key={severity} value={severity}>
              {severity}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="bug-archived-filter" className="block text-sm font-medium">
          Status filter
        </label>
        <select
          id="bug-archived-filter"
          value={value.archived}
          onChange={(event) => onChange({ archived: event.target.value as BugFiltersValue["archived"] })}
          className="mt-1 rounded border px-2 py-2"
        >
          <option value="false">Active</option>
          <option value="true">Archived</option>
          <option value="all">All</option>
        </select>
      </div>

      <div className="flex items-center gap-2 pb-2">
        <input
          id="bug-unassigned-filter"
          type="checkbox"
          checked={value.unassigned}
          onChange={(event) => onChange({ unassigned: event.target.checked })}
        />
        <label htmlFor="bug-unassigned-filter" className="text-sm font-medium">
          Unassigned only
        </label>
      </div>

      <div>
        <label htmlFor="bug-sort" className="block text-sm font-medium">
          Sort
        </label>
        <select
          id="bug-sort"
          value={value.ordering}
          onChange={(event) => onChange({ ordering: event.target.value })}
          className="mt-1 rounded border px-2 py-2"
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
