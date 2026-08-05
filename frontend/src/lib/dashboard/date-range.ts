export type DateRangePreset = "7d" | "30d" | "90d" | "custom";

export const PRESET_LABELS: Record<Exclude<DateRangePreset, "custom">, string> = {
  "7d": "Last 7 days",
  "30d": "Last 30 days",
  "90d": "Last 90 days",
};

const PRESET_DAYS: Record<Exclude<DateRangePreset, "custom">, number> = {
  "7d": 7,
  "30d": 30,
  "90d": 90,
};

// Local calendar date (YYYY-MM-DD), not UTC — Date#toISOString() reports
// UTC, which would read as "yesterday" for any visitor west of UTC in the
// evening.
export function toISODate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function isValidISODate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00`);
  return !Number.isNaN(date.getTime()) && toISODate(date) === value;
}

// "Last N days" = today plus the previous (N-1) calendar days — an N-day
// inclusive span. "Last 7 days" is today + the previous 6 days, never an
// accidental 8-day range.
export function computePresetRange(
  preset: Exclude<DateRangePreset, "custom">,
  today: Date,
): { date_from: string; date_to: string } {
  const days = PRESET_DAYS[preset];
  const from = new Date(today);
  from.setDate(from.getDate() - (days - 1));
  return { date_from: toISODate(from), date_to: toISODate(today) };
}

export function isReversedRange(date_from: string, date_to: string): boolean {
  return date_from > date_to;
}

const MAX_CUSTOM_RANGE_DAYS = 366;

export function isExcessiveRange(date_from: string, date_to: string): boolean {
  if (!isValidISODate(date_from) || !isValidISODate(date_to)) return false;
  const from = new Date(`${date_from}T00:00:00`);
  const to = new Date(`${date_to}T00:00:00`);
  const days = Math.round((to.getTime() - from.getTime()) / (24 * 60 * 60 * 1000));
  return days > MAX_CUSTOM_RANGE_DAYS - 1;
}
