// Duration/date/number formatting shared across every dashboard section, so
// the same 90-day-old bug never reads as "90d" in one chart and "3mo" in
// another. Every call passes an explicit locale ("en-US") rather than
// relying on the runtime's default — the server-rendering process and the
// visitor's browser can have different default locales, which would
// otherwise produce a hydration mismatch on the very first render.

export function formatDuration(totalSeconds: number | null): string {
  if (totalSeconds === null) return "No data";
  if (totalSeconds < 60) return "<1m";

  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);

  if (days > 0) return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
  if (hours > 0) return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
  return `${minutes}m`;
}

export function formatShortDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(isoDateTime: string): string {
  return new Date(isoDateTime).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

export function formatStatusLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
