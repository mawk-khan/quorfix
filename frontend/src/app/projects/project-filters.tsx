"use client";

import { SearchInput } from "@/components/ui/search-input";
import { Select } from "@/components/ui/select";
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
    <div className="flex flex-wrap items-end gap-4">
      <div className="min-w-48 flex-1">
        <label htmlFor="project-search" className="block text-sm font-medium text-text-primary">
          Search
        </label>
        <SearchInput
          id="project-search"
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Name or key"
          className="mt-1.5"
        />
      </div>
      <div>
        <label htmlFor="project-archived-filter" className="block text-sm font-medium text-text-primary">
          Status
        </label>
        <Select
          id="project-archived-filter"
          value={archived}
          onChange={(event) => onArchivedChange(event.target.value as ArchivedFilter)}
          className="mt-1.5 w-32"
        >
          <option value="false">Active</option>
          <option value="true">Archived</option>
          <option value="all">All</option>
        </Select>
      </div>
    </div>
  );
}
