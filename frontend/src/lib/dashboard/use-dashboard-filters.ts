"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useSyncExternalStore } from "react";

import {
  computePresetRange,
  isValidISODate,
  type DateRangePreset,
} from "./date-range";

const VALID_PRESETS: DateRangePreset[] = ["7d", "30d", "90d", "custom"];
const DEFAULT_PRESET: Exclude<DateRangePreset, "custom"> = "30d";

// useSyncExternalStore, not useState+useEffect: the snapshot answers "are we
// past hydration" — false on both the server render and the client's first
// (hydrating) render, flipping to true only once React confirms the client
// has taken over. That's the mechanism this hook actually needs to avoid a
// hydration mismatch on "today" (see below), without the cascading-render
// footgun of calling setState from inside an effect body.
function subscribeNoop() {
  return () => {};
}
function getClientSnapshot() {
  return true;
}
function getServerSnapshot() {
  return false;
}

export interface DashboardFiltersValue {
  range: DateRangePreset;
  date_from: string;
  date_to: string;
  project: string;
}

export interface DashboardFiltersUpdate {
  range?: DateRangePreset;
  date_from?: string;
  date_to?: string;
  project?: string;
}

export interface UseDashboardFiltersResult {
  // False until the client-only "today" is resolved (see below) — callers
  // must not fire date-ranged queries or render computed dates while this
  // is false.
  ready: boolean;
  filters: DashboardFiltersValue;
  updateFilters: (next: DashboardFiltersUpdate) => void;
}

function parseRange(raw: string | null): DateRangePreset {
  return raw && (VALID_PRESETS as string[]).includes(raw) ? (raw as DateRangePreset) : DEFAULT_PRESET;
}

export function useDashboardFilters(): UseDashboardFiltersResult {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // "Today" is only knowable on the client — computing it during the
  // render that produces the initial HTML (which can run on a server in a
  // different timezone than the visitor's browser) would let that
  // server-rendered preset date range disagree with the client's own
  // computation of "today", producing a hydration mismatch. `today` stays
  // null until isClient flips true post-hydration, so the very first
  // client render matches the server render exactly.
  const isClient = useSyncExternalStore(subscribeNoop, getClientSnapshot, getServerSnapshot);
  const today = isClient ? new Date() : null;

  const range = parseRange(searchParams.get("range"));
  const project = searchParams.get("project") ?? "";

  const rawFrom = searchParams.get("from");
  const rawTo = searchParams.get("to");
  const explicitCustomRangeInUrl =
    range === "custom" && rawFrom && rawTo && isValidISODate(rawFrom) && isValidISODate(rawTo);

  // Only a preset range needs to wait on the client-only "today" — an
  // explicit custom range read straight from the URL is already
  // deterministic between server and client.
  const ready = today !== null || Boolean(explicitCustomRangeInUrl);

  let date_from = "";
  let date_to = "";
  if (explicitCustomRangeInUrl && rawFrom && rawTo) {
    date_from = rawFrom;
    date_to = rawTo;
  } else if (today !== null) {
    const presetForComputation = range !== "custom" ? range : DEFAULT_PRESET;
    const computed = computePresetRange(presetForComputation, today);
    date_from = computed.date_from;
    date_to = computed.date_to;
  }

  function updateFilters(next: DashboardFiltersUpdate) {
    const params = new URLSearchParams(searchParams.toString());
    const merged: DashboardFiltersValue = {
      range,
      date_from,
      date_to,
      project,
      ...next,
    };

    if (merged.range !== DEFAULT_PRESET) params.set("range", merged.range);
    else params.delete("range");

    if (merged.range === "custom") {
      params.set("from", merged.date_from);
      params.set("to", merged.date_to);
    } else {
      params.delete("from");
      params.delete("to");
    }

    if (merged.project) params.set("project", merged.project);
    else params.delete("project");

    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  return { ready, filters: { range, date_from, date_to, project }, updateFilters };
}
