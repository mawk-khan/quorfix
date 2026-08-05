"use client";

import { useState } from "react";

import type { ActiveProject } from "@/lib/api/types";
import {
  isExcessiveRange,
  isReversedRange,
  isValidISODate,
  PRESET_LABELS,
  type DateRangePreset,
} from "@/lib/dashboard/date-range";
import type {
  DashboardFiltersUpdate,
  DashboardFiltersValue,
} from "@/lib/dashboard/use-dashboard-filters";

const PRESETS: Exclude<DateRangePreset, "custom">[] = ["7d", "30d", "90d"];

interface DashboardFiltersProps {
  filters: DashboardFiltersValue;
  projects: ActiveProject[];
  onChange: (next: DashboardFiltersUpdate) => void;
}

export function DashboardFilters({ filters, projects, onChange }: DashboardFiltersProps) {
  // Local draft for the custom-range inputs so a half-typed date never
  // fires a request — committed to the URL (and every date-ranged query)
  // only via the explicit "Apply" action, after passing validation.
  const [draftFrom, setDraftFrom] = useState(filters.date_from);
  const [draftTo, setDraftTo] = useState(filters.date_to);
  const [error, setError] = useState<string | null>(null);

  function selectPreset(preset: Exclude<DateRangePreset, "custom">) {
    setError(null);
    onChange({ range: preset });
  }

  function selectCustom() {
    setDraftFrom(filters.date_from);
    setDraftTo(filters.date_to);
    setError(null);
    onChange({ range: "custom", date_from: filters.date_from, date_to: filters.date_to });
  }

  function applyCustomRange() {
    if (!isValidISODate(draftFrom) || !isValidISODate(draftTo)) {
      setError("Enter two valid dates.");
      return;
    }
    if (isReversedRange(draftFrom, draftTo)) {
      setError("The end date must not be before the start date.");
      return;
    }
    if (isExcessiveRange(draftFrom, draftTo)) {
      setError("Custom date ranges are limited to 366 days.");
      return;
    }
    setError(null);
    onChange({ range: "custom", date_from: draftFrom, date_to: draftTo });
  }

  return (
    <div className="flex flex-wrap items-end gap-4">
      <fieldset className="flex flex-wrap items-end gap-2">
        <legend className="mb-1 block text-sm font-medium">Date range</legend>
        {PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => selectPreset(preset)}
            aria-pressed={filters.range === preset}
            className={`rounded border px-3 py-1.5 text-sm ${
              filters.range === preset ? "border-blue-600 bg-blue-50 font-medium text-blue-700" : ""
            }`}
          >
            {PRESET_LABELS[preset]}
          </button>
        ))}
        <button
          type="button"
          onClick={selectCustom}
          aria-pressed={filters.range === "custom"}
          className={`rounded border px-3 py-1.5 text-sm ${
            filters.range === "custom" ? "border-blue-600 bg-blue-50 font-medium text-blue-700" : ""
          }`}
        >
          Custom
        </button>
      </fieldset>

      {filters.range === "custom" && (
        <div className="flex items-end gap-2">
          <div>
            <label htmlFor="dashboard-date-from" className="block text-sm font-medium">
              From
            </label>
            <input
              id="dashboard-date-from"
              type="date"
              value={draftFrom}
              onChange={(event) => setDraftFrom(event.target.value)}
              className="mt-1 rounded border px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label htmlFor="dashboard-date-to" className="block text-sm font-medium">
              To
            </label>
            <input
              id="dashboard-date-to"
              type="date"
              value={draftTo}
              onChange={(event) => setDraftTo(event.target.value)}
              className="mt-1 rounded border px-2 py-1.5 text-sm"
            />
          </div>
          <button type="button" onClick={applyCustomRange} className="rounded border px-3 py-1.5 text-sm">
            Apply
          </button>
        </div>
      )}

      <div>
        <label htmlFor="dashboard-project-filter" className="block text-sm font-medium">
          Project
        </label>
        <select
          id="dashboard-project-filter"
          value={filters.project}
          onChange={(event) => onChange({ project: event.target.value })}
          className="mt-1 rounded border px-2 py-1.5 text-sm"
        >
          <option value="">All projects</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.key}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <p role="alert" className="w-full text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
