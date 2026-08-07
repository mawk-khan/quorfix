"use client";

import { useEffect } from "react";

import { pageTitle, PRODUCT_NAME } from "@/lib/branding";

/**
 * Sets the browser tab title from a client component. Every page.tsx in
 * this app is a client component (interactivity via TanStack Query/React
 * Hook Form throughout), so Next's server-only `export const metadata`
 * isn't available here — this is a plain post-hydration side effect
 * instead (document.title is never part of React's reconciled DOM tree),
 * which is what keeps this from introducing any hydration mismatch: the
 * server-rendered HTML's <title> (the root layout's static default, see
 * app/layout.tsx) is left untouched during hydration and only updated
 * afterward, in an effect, exactly like any other browser-only API.
 *
 * Pass undefined to leave the current title (typically the root layout's
 * default, "Quorfix") alone — e.g. a page whose title only becomes known
 * once data has loaded.
 */
export function usePageTitle(title: string | undefined): void {
  useEffect(() => {
    if (title === undefined) return;
    document.title = pageTitle(title);
    return () => {
      document.title = PRODUCT_NAME;
    };
  }, [title]);
}
