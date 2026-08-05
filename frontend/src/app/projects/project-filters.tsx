"use client";

import type { ArchivedFilter } from "@/lib/api/types";

interface ProjectFiltersProps {
  search: string;
  archived: ArchivedFilter;
  onSearchChange: (value: string) => void;
  onArchivedChange: (value: ArchivedFilter) => void;
}

export function ProjectFilters({
  search,
  archived,
  onSearchChange,
  onArchivedChange,
}: ProjectFiltersProps) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <label htmlFor="project-search" className="block text-sm font-medium">
          Search
        </label>
        <input
          id="project-search"
          type="search"
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Name or key"
          className="mt-1 rounded border px-3 py-2"
        />
      </div>
      <div>
        <label htmlFor="project-archived-filter" className="block text-sm font-medium">
          Status
        </label>
        <select
          id="project-archived-filter"
          value={archived}
          onChange={(event) => onArchivedChange(event.target.value as ArchivedFilter)}
          className="mt-1 rounded border px-2 py-2"
        >
          <option value="false">Active</option>
          <option value="true">Archived</option>
          <option value="all">All</option>
        </select>
      </div>
    </div>
  );
}
