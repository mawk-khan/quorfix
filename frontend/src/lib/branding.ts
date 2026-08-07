// Single source of truth for static product-facing text — a plain
// constant, not a runtime-configurable value, since this is branding, not
// per-deployment configuration (see backend/config/settings/base.py's
// PRODUCT_NAME for the backend equivalent). Import from here rather than
// hardcoding "Quorfix" again at each call site.

export const PRODUCT_NAME = "Quorfix";

export const PRODUCT_TAGLINE = "Open-core bug tracking for software teams";

/** Browser tab title for a specific page, e.g. pageTitle("Sign in") -> "Sign in · Quorfix". */
export function pageTitle(page: string): string {
  return `${page} · ${PRODUCT_NAME}`;
}
