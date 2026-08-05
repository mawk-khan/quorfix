// Values from the dataviz skill's validated reference palette
// (references/palette.md) — light mode only, matching this app's current
// styling (no dark-mode system exists anywhere else in the app yet, so
// this doesn't introduce a half-implemented one). Categorical slots 1
// (blue) and 2 (orange) are the palette's own adjacent-safe pair (worst
// adjacent CVD ΔE 9.1, normal-vision ΔE 19.6 — both clear the validator's
// gates), used for the trends chart's two series.

export const CHART_COLORS = {
  seriesCreated: "#2a78d6", // categorical slot 1 — blue
  seriesResolved: "#eb6834", // categorical slot 2 — orange
  singleMeasure: "#2a78d6", // one hue for single-series bars (resolution time, status, severity)
  grid: "#e1e0d9", // hairline gridline
  axis: "#c3c2b7", // baseline/axis
  textMuted: "#898781", // axis tick labels
  textSecondary: "#52514e",
  textPrimary: "#0b0b0b",
  surface: "#fcfcfb",
} as const;
