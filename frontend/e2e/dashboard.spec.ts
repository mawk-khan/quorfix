import { expect, test, type Page } from "@playwright/test";

// Deliberately independent of every other spec file's fixtures (team-
// journey's "Acme", bug-lifecycle's "bug-e2e-...", etc.) — this spec's
// organization, users, project, and bugs come from a dedicated fixture
// (apps/core/management/commands/seed_e2e_analytics_fixture.py), seeded
// once by global-setup.ts before any spec file runs. All credentials below
// are namespaced ("analytics-e2e-...") specifically so they can never
// collide with another spec's fixtures regardless of file execution order.
//
// Expected values below mirror the fixture command's own documented
// numbers exactly (see FIXTURE_BUGS's docstring there) — if either drifts,
// apps/core/tests/test_seed_e2e_analytics_fixture.py catches it first,
// with a much faster feedback loop than this suite.
const ADMIN_EMAIL = "analytics-e2e-admin@example.com";
const VIEWER_EMAIL = "analytics-e2e-viewer@example.com";
const PASSWORD = "AnalyticsE2EPass123!";
const PROJECT_LABEL = "ANLY";

async function signIn(page: Page, email: string) {
  await page.goto("/sign-in");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await expect(page).toHaveURL("/");
}

async function expectSummary(
  page: Page,
  { open, overdue, newBugs, resolved }: { open: string; overdue: string; newBugs: string; resolved: string },
) {
  await expect(page.getByTestId("summary-open_bugs")).toHaveText(open);
  await expect(page.getByTestId("summary-overdue_bugs")).toHaveText(overdue);
  await expect(page.getByTestId("summary-new_bugs")).toHaveText(newBugs);
  await expect(page.getByTestId("summary-resolved_bugs")).toHaveText(resolved);
}

test.describe.serial("analytics dashboard", () => {
  test("administrator sees the dashboard with meaningful, correct default (30-day) values", async ({
    page,
  }) => {
    await signIn(page, ADMIN_EMAIL);

    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    // Open/overdue are point-in-time and never change with the date range;
    // new/resolved use the default 30-day preset.
    await expectSummary(page, { open: "5", overdue: "1", newBugs: "8", resolved: "3" });

    // Workload and active-projects, both point-in-time, from the fixture.
    await expect(page.getByRole("heading", { name: "Bugs per developer" })).toBeVisible();
    await expect(page.getByText(/analytics e2e developer/i)).toBeVisible();
    await expect(page.getByRole("link", { name: PROJECT_LABEL, exact: true })).toBeVisible();
  });

  test("the 7-day preset narrows new/resolved without moving open/overdue", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);

    await page.getByRole("button", { name: "Last 7 days" }).click();
    await expectSummary(page, { open: "5", overdue: "1", newBugs: "6", resolved: "1" });
  });

  test("the 90-day preset shows the full fixture (nothing falls outside 90 days)", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);

    await page.getByRole("button", { name: "Last 90 days" }).click();
    await expectSummary(page, { open: "5", overdue: "1", newBugs: "8", resolved: "3" });
  });

  test("the project filter narrows the dashboard to that project without erroring", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);

    await page.getByLabel(/project/i).selectOption({ label: PROJECT_LABEL });
    // The fixture has exactly one project, so filtering to it changes
    // nothing numerically — this asserts the control round-trips through a
    // real request without breaking the page, not that it narrows further.
    await expectSummary(page, { open: "5", overdue: "1", newBugs: "8", resolved: "3" });
  });

  test("an empty custom range shows explicit empty states, not blank charts", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);

    await page.getByRole("button", { name: "Custom" }).click();
    await page.getByLabel(/^from$/i).fill("2020-01-01");
    await page.getByLabel(/^to$/i).fill("2020-01-02");
    await page.getByRole("button", { name: "Apply" }).click();

    await expectSummary(page, { open: "5", overdue: "1", newBugs: "0", resolved: "0" });
    await expect(page.getByText(/no bugs were created or resolved in this range/i)).toBeVisible();
  });

  test("distributions reflect the fixture's current backlog", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);

    const statusTable = page.getByRole("table", { name: /current bugs by status/i });
    await expect(statusTable.getByRole("row", { name: /^new 1$/i })).toBeVisible();
    await expect(statusTable.getByRole("row", { name: /^in progress 1$/i })).toBeVisible();
    await expect(statusTable.getByRole("row", { name: /^resolved 2$/i })).toBeVisible();

    const severityTable = page.getByRole("table", { name: /ranked blocker to trivial/i });
    await expect(severityTable.getByRole("row", { name: /^blocker 1$/i })).toBeVisible();
    await expect(severityTable.getByRole("row", { name: /^critical 1$/i })).toBeVisible();
  });

  test("viewer can open the dashboard, read-only", async ({ page }) => {
    await signIn(page, VIEWER_EMAIL);

    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expectSummary(page, { open: "5", overdue: "1", newBugs: "8", resolved: "3" });
    // Read-only: the dashboard has no create/edit controls of its own —
    // only filters and links out to /bugs and /projects.
    await expect(page.getByRole("button", { name: /^(create|edit|delete)/i })).toHaveCount(0);
  });

  test("no Professional-only controls appear anywhere on the dashboard", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);

    for (const proText of [
      "Custom fields",
      "Saved views",
      "SLA",
      "Automation rules",
      "Webhooks",
      "API tokens",
      "SSO",
      "SCIM",
      "White label",
      "Scheduled reports",
      "Export to CSV",
      "Export to PDF",
    ]) {
      // Word-boundary regex, not a bare substring: getByText concatenates
      // adjacent sibling elements' text with no separator (e.g. "...Last 30
      // days" + "Last 90 days..." reads as "...daysLast..."), which lets a
      // short string like "SLA" false-positive-match across element
      // boundaries ("day**sLa**st"). \b requires SLA to sit at an actual
      // word edge, which that concatenation never produces.
      const pattern = new RegExp(`\\b${proText.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
      await expect(page.getByText(pattern)).toHaveCount(0);
    }
  });
});
