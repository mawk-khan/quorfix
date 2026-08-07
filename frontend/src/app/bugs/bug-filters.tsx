"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { SearchInput } from "@/components/ui/search-input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/cn";
import type { Project } from "@/lib/api/types";
import { BUG_PRIORITIES, BUG_SEVERITIES } from "@/lib/validation/bugs";

import { PRIORITY_LABELS, SEVERITY_LABELS, STATUS_LABELS } from "./bug-badges";

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

// Same height/radius/focus-ring contract as Select/Input, applied directly
// (not through the Select component) — a multi-select listbox already shows
// its own open list of options, so Select's dropdown chevron affordance
// would be misleading here.
const MULTISELECT_CLASSNAME =
  "rounded-field border border-border bg-surface px-3 py-2 text-sm text-text-primary " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:border-primary";

export function BugFilters({ value, projects, onChange }: BugFiltersProps) {
  return (
    <div className="flex flex-wrap items-end gap-4">
      <div className="min-w-48 flex-1">
        <label htmlFor="bug-search" className="block text-sm font-medium text-text-primary">
          Search
        </label>
        <SearchInput
          id="bug-search"
          value={value.search}
          onChange={(event) => onChange({ search: event.target.value })}
          placeholder="Key or title"
          className="mt-1.5"
        />
      </div>

      <div>
        <label htmlFor="bug-project-filter" className="block text-sm font-medium text-text-primary">
          Project
        </label>
        <Select
          id="bug-project-filter"
          value={value.project}
          onChange={(event) => onChange({ project: event.target.value })}
          className="mt-1.5 w-40"
        >
          <option value="">All projects</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.key}
            </option>
          ))}
        </Select>
      </div>

      <div>
        <label htmlFor="bug-status-filter" className="block text-sm font-medium text-text-primary">
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
          className={cn(MULTISELECT_CLASSNAME, "mt-1.5 w-40")}
        >
          {BUG_STATUSES.map((status) => (
            <option key={status} value={status}>
              {STATUS_LABELS[status]}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="bug-priority-filter" className="block text-sm font-medium text-text-primary">
          Priority
        </label>
        <Select
          id="bug-priority-filter"
          value={value.priority}
          onChange={(event) => onChange({ priority: event.target.value })}
          className="mt-1.5 w-32"
        >
          <option value="">Any</option>
          {BUG_PRIORITIES.map((priority) => (
            <option key={priority} value={priority}>
              {PRIORITY_LABELS[priority]}
            </option>
          ))}
        </Select>
      </div>

      <div>
        <label htmlFor="bug-severity-filter" className="block text-sm font-medium text-text-primary">
          Severity
        </label>
        <Select
          id="bug-severity-filter"
          value={value.severity}
          onChange={(event) => onChange({ severity: event.target.value })}
          className="mt-1.5 w-32"
        >
          <option value="">Any</option>
          {BUG_SEVERITIES.map((severity) => (
            <option key={severity} value={severity}>
              {SEVERITY_LABELS[severity]}
            </option>
          ))}
        </Select>
      </div>

      <div>
        <label htmlFor="bug-archived-filter" className="block text-sm font-medium text-text-primary">
          Status filter
        </label>
        <Select
          id="bug-archived-filter"
          value={value.archived}
          onChange={(event) => onChange({ archived: event.target.value as BugFiltersValue["archived"] })}
          className="mt-1.5 w-32"
        >
          <option value="false">Active</option>
          <option value="true">Archived</option>
          <option value="all">All</option>
        </Select>
      </div>

      <div>
        <label htmlFor="bug-sort" className="block text-sm font-medium text-text-primary">
          Sort
        </label>
        <Select
          id="bug-sort"
          value={value.ordering}
          onChange={(event) => onChange({ ordering: event.target.value })}
          className="mt-1.5 w-48"
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </div>

      <div className="flex h-10 items-center gap-2">
        <Checkbox
          id="bug-unassigned-filter"
          checked={value.unassigned}
          onChange={(event) => onChange({ unassigned: event.target.checked })}
        />
        <label htmlFor="bug-unassigned-filter" className="text-sm font-medium text-text-primary">
          Unassigned only
        </label>
      </div>
    </div>
  );
}
