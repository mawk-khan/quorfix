import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Reuses the analytics-e2e fixture (seeded once, idempotently, by global-
// setup.ts) rather than creating a new one — it already has an
// administrator, a project, and bugs in every status, which is exactly the
// authenticated content this spec needs to scan. Namespaced independently
// of every other spec's fixtures, so this file has no dependency on
// execution order and no other spec depends on it.
const ADMIN_EMAIL = "analytics-e2e-admin@example.com";
const PASSWORD = "AnalyticsE2EPass123!";

async function signIn(page: Page) {
  await page.goto("/sign-in");
  await page.getByLabel(/email/i).fill(ADMIN_EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await expect(page).toHaveURL("/");
}

// Only serious/critical violations fail the build — moderate/minor findings
// are real but noisier and more debatable to act on automatically; this
// keeps the gate meaningful rather than something a team learns to ignore.
// No rules are disabled: every axe rule runs, on every scanned page.
async function expectNoSeriousViolations(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).analyze();
  const serious = results.violations.filter(
    (violation) => violation.impact === "serious" || violation.impact === "critical",
  );

  if (serious.length > 0) {
    const report = serious
      .map((violation) => {
        const nodes = violation.nodes.map((node) => `    - ${node.target.join(" ")}`).join("\n");
        return (
          `[${violation.impact}] ${violation.id}: ${violation.help}\n` +
          `  ${violation.helpUrl}\n` +
          `  Affected elements:\n${nodes}`
        );
      })
      .join("\n\n");
    expect(serious, `Serious/critical axe violations on ${label}:\n\n${report}`).toEqual([]);
  }
}

test.describe("accessibility scans", () => {
  test("sign-in page (unauthenticated)", async ({ page }) => {
    await page.goto("/sign-in");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expectNoSeriousViolations(page, "/sign-in");
  });

  test("dashboard (authenticated)", async ({ page }) => {
    await signIn(page);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    // Each dashboard section resolves its own query independently — wait
    // for a chart's heading rather than the page's own heading, so the
    // scan runs against real content instead of the section's loading
    // skeleton (which is deliberately aria-hidden and would otherwise
    // still be present, mid-fetch, the instant the page heading appears).
    await expect(page.getByRole("heading", { name: "Bugs by status" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Bug trends" })).toBeVisible();
    await expectNoSeriousViolations(page, "/ (dashboard)");
  });

  test("projects list (authenticated)", async ({ page }) => {
    await signIn(page);
    await page.goto("/projects");
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByRole("link", { name: "Analytics E2E Project" })).toBeVisible();
    await expectNoSeriousViolations(page, "/projects");
  });

  test("bugs list (authenticated)", async ({ page }) => {
    await signIn(page);
    await page.goto("/bugs");
    await expect(page.getByRole("heading", { name: "Bugs", exact: true })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible();
    await expectNoSeriousViolations(page, "/bugs");
  });

  test("bug detail (authenticated)", async ({ page }) => {
    await signIn(page);
    await page.goto("/bugs");
    await expect(page.getByRole("table")).toBeVisible();
    // Navigated to via the list, not a hardcoded id — this fixture's bug
    // ids aren't fixed/documented the way its counts are, and a link click
    // is what a real user (and this spec's own "reachable via keyboard/
    // mouse equivalence" concern) actually does.
    await page.getByRole("table").getByRole("link").first().click();
    await expect(page.getByRole("heading", { name: "Details" })).toBeVisible();
    await expectNoSeriousViolations(page, "/bugs/:id");
  });

  test("notifications list (authenticated)", async ({ page }) => {
    await signIn(page);
    await page.goto("/notifications");
    await expect(page.getByRole("heading", { name: "Notifications" })).toBeVisible();
    await expectNoSeriousViolations(page, "/notifications");
  });

  test("notification preferences (authenticated)", async ({ page }) => {
    await signIn(page);
    await page.goto("/notifications/preferences");
    await expect(page.getByRole("heading", { name: /email notification preferences/i })).toBeVisible();
    await expectNoSeriousViolations(page, "/notifications/preferences");
  });
});
