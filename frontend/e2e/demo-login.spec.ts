import { expect, test } from "@playwright/test";

import { apiGet } from "./notification-helpers";

// The "Quorfix Demo" organization and its five personas are seeded
// unconditionally by global-setup.ts (seed_e2e_demo_login_fixture), same as
// every other spec's fixture. What is NOT set unconditionally is
// QUORFIX_DEMO_MODE itself: it's a plain env var read once when the backend
// process starts, so — unlike data — this suite can't flip it on its own
// without restarting the shared backend container mid-run, which would
// affect every other spec sharing it. This spec instead probes the session
// response and skips itself with a clear message when demo mode isn't
// enabled for this particular run, rather than failing the suite. See
// docs/ACCESS_AND_TESTING.md "Demo Quick Access (role login)" for how to
// enable it locally before running this spec.
test("explore as Developer, switch role, then sign in as Viewer", async ({ page }) => {
  await page.goto("/sign-in");

  const session = await apiGet<{ demo_mode: boolean }>(page, "/api/auth/session/");
  test.skip(
    session.demo_mode !== true,
    "QUORFIX_DEMO_MODE is not enabled for this e2e run — set QUORFIX_DEMO_MODE=true in " +
      ".env and restart the backend container before running this spec.",
  );

  await expect(page.getByRole("heading", { name: "Explore Quorfix" })).toBeVisible();

  await page.getByRole("button", { name: "Developer", exact: true }).click();
  await expect(page).toHaveURL("/");
  await expect(page.getByText(/exploring quorfix as developer/i)).toBeVisible();
  await expect(page.getByText(/signed in as developer@quorfix\.local/i)).toBeVisible();

  await page.getByRole("button", { name: /switch role/i }).click();
  await expect(page).toHaveURL("/sign-in");
  await expect(page.getByRole("heading", { name: "Explore Quorfix" })).toBeVisible();

  await page.getByRole("button", { name: "Viewer", exact: true }).click();
  await expect(page).toHaveURL("/");
  await expect(page.getByText(/exploring quorfix as viewer/i)).toBeVisible();
  await expect(page.getByText(/signed in as viewer@quorfix\.local/i)).toBeVisible();
});
