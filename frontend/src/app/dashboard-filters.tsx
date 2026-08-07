"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/cn";
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

// Toggle-button chrome (not the standalone Button component — these need a
// persistent "selected" look driven by aria-pressed, which Button's variant
// set doesn't model): same height/radius/focus-ring contract as Button's sm
// size, so it still reads as one family.
const TOGGLE_BASE =
  "inline-flex h-8 items-center justify-center rounded-field border px-3 text-sm font-medium " +
  "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-surface";
const TOGGLE_ACTIVE = "border-primary bg-primary-subtle text-primary";
const TOGGLE_INACTIVE = "border-border bg-surface text-text-secondary hover:bg-page hover:text-text-primary";

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
        <legend className="mb-1.5 block text-sm font-medium text-text-primary">Date range</legend>
        {PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => selectPreset(preset)}
            aria-pressed={filters.range === preset}
            className={cn(TOGGLE_BASE, filters.range === preset ? TOGGLE_ACTIVE : TOGGLE_INACTIVE)}
          >
            {PRESET_LABELS[preset]}
          </button>
        ))}
        <button
          type="button"
          onClick={selectCustom}
          aria-pressed={filters.range === "custom"}
          className={cn(TOGGLE_BASE, filters.range === "custom" ? TOGGLE_ACTIVE : TOGGLE_INACTIVE)}
        >
          Custom
        </button>
      </fieldset>

      {filters.range === "custom" && (
        <div className="flex items-end gap-2">
          <div>
            <label htmlFor="dashboard-date-from" className="block text-sm font-medium text-text-primary">
              From
            </label>
            <Input
              id="dashboard-date-from"
              type="date"
              value={draftFrom}
              onChange={(event) => setDraftFrom(event.target.value)}
              className="mt-1.5 h-8"
            />
          </div>
          <div>
            <label htmlFor="dashboard-date-to" className="block text-sm font-medium text-text-primary">
              To
            </label>
            <Input
              id="dashboard-date-to"
              type="date"
              value={draftTo}
              onChange={(event) => setDraftTo(event.target.value)}
              className="mt-1.5 h-8"
            />
          </div>
          <Button type="button" variant="secondary" size="sm" onClick={applyCustomRange}>
            Apply
          </Button>
        </div>
      )}

      <div>
        <label htmlFor="dashboard-project-filter" className="block text-sm font-medium text-text-primary">
          Project
        </label>
        <Select
          id="dashboard-project-filter"
          value={filters.project}
          onChange={(event) => onChange({ project: event.target.value })}
          className="mt-1.5 h-8 w-auto"
        >
          <option value="">All projects</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.key}
            </option>
          ))}
        </Select>
      </div>

      {error && (
        <p role="alert" className="w-full text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
