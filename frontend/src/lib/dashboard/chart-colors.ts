// Structural values (grid/axis/text/surface) are aliases of this app's own
// design tokens (see app/globals.css's @theme block) — not a separate
// palette, so charts render in the same cool-gray system as every card,
// border, and label elsewhere in Quorfix. seriesCreated/singleMeasure use
// the brand primary. The one exception is seriesResolved: kept as the
// dataviz skill's validated categorical-slot-2 orange (blue vs. orange is
// the classic CVD-safe pairing — orthogonal to the red-green confusion
// axis that affects most color vision deficiency, so shifting the exact
// blue shade to the brand primary doesn't threaten that separation).
//
// Light mode only — no dark-mode system exists anywhere else in the app
// yet, so this doesn't introduce a half-implemented one.
//
// textMuted is deliberately absent here: axis tick labels are real
// information (not decorative), so they use textSecondary — the same
// 7.5:1-contrast token every other real label in the app uses — never the
// muted token, which globals.css documents as decorative-only.

export const CHART_COLORS = {
  seriesCreated: "#375dfb", // brand primary
  seriesResolved: "#eb6834", // dataviz skill's validated categorical slot 2 — orange
  singleMeasure: "#375dfb", // one hue for single-series bars (resolution time, status, severity)
  grid: "#e5e7eb", // = --color-border
  axis: "#d1d5db", // = --color-border-strong
  textSecondary: "#475569", // = --color-text-secondary — axis tick labels
  textPrimary: "#0a0d14", // = --color-text-primary — tooltip text
  surface: "#ffffff", // = --color-surface
} as const;
