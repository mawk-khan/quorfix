import { expect, test, type Page } from "@playwright/test";

// Deliberately does NOT rely on team-journey.spec.ts or
// team-project-lifecycle.spec.ts having run first (or at all) — this spec's
// organization, users, and project come from a dedicated fixture
// (apps/core/management/commands/seed_e2e_bug_fixture.py), seeded once by
// global-setup.ts before any spec file runs, entirely independent of
// whatever those other specs create. All credentials below are namespaced
// ("bug-e2e-...") specifically so they can never collide with another
// spec's fixtures regardless of file execution order.
const ADMIN_EMAIL = "bug-e2e-admin@example.com";
const DEVELOPER_EMAIL = "bug-e2e-developer@example.com";
const DEVELOPER_LABEL = `E2E Developer (${DEVELOPER_EMAIL})`;
const REPORTER_EMAIL = "bug-e2e-reporter@example.com";
const VIEWER_EMAIL = "bug-e2e-viewer@example.com";
const PASSWORD = "BugE2EPass123!";
const PROJECT_LABEL = "BEP — Bug E2E Project";

async function signIn(page: Page, email: string) {
  await page.goto("/sign-in");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await expect(page).toHaveURL("/");
}

async function createBug(page: Page, title: string): Promise<string> {
  await signIn(page, REPORTER_EMAIL);
  await page.goto("/bugs/new");
  await expect(page.getByRole("form", { name: /create bug/i })).toBeVisible({ timeout: 15000 });
  await page.getByLabel(/^project$/i).selectOption({ label: PROJECT_LABEL });
  await page.getByLabel(/^title$/i).fill(title);
  await page.getByRole("button", { name: /create bug/i }).click();

  await expect(page.getByRole("heading", { name: title })).toBeVisible({ timeout: 15000 });
  const id = new URL(page.url()).pathname.split("/").filter(Boolean).pop() ?? "";
  expect(id).not.toBe("");
  return id;
}

let bugAId = "";

test.describe.serial("bug lifecycle", () => {
  test("a reporter creates a bug", async ({ page }) => {
    bugAId = await createBug(page, "App crashes on save");
  });

  test("an admin triages the bug", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);
    await page.goto(`/bugs/${bugAId}`);

    await page.getByLabel(/new status/i).selectOption("triaged");
    await page.getByRole("button", { name: /^apply$/i }).click();
    await expect(page.getByText(/^triaged$/i)).toBeVisible();
  });

  test("an admin assigns the bug to a developer, then transitions it to assigned", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);
    await page.goto(`/bugs/${bugAId}`);

    await page.getByLabel(/^assignee$/i).selectOption({ label: DEVELOPER_LABEL });
    await page.getByRole("button", { name: /update assignee/i }).click();
    // Waiting on the <select>'s own checked option is NOT sufficient here —
    // a native <select> reflects the user's choice immediately, regardless
    // of whether the mutation it's wired to actually succeeded yet. Waiting
    // on "Currently assigned to" (driven by bug.assignee from the server
    // response, not the form's local state) ensures the assign mutation has
    // truly landed — and with it, the version bump the next step's
    // transition depends on — before we move on.
    await expect(page.getByTestId("current-assignee")).toHaveText(/E2E Developer/);

    await page.getByLabel(/new status/i).selectOption("assigned");
    await page.getByRole("button", { name: /^apply$/i }).click();
    await expect(page.getByText(/^assigned$/i)).toBeVisible();
  });

  test("the developer moves the bug through in_progress to resolved", async ({ page }) => {
    await signIn(page, DEVELOPER_EMAIL);
    await page.goto(`/bugs/${bugAId}`);

    await page.getByLabel(/new status/i).selectOption("in_progress");
    await page.getByRole("button", { name: /^apply$/i }).click();
    await expect(page.getByText(/in progress/i)).toBeVisible();

    await page.getByLabel(/new status/i).selectOption("resolved");
    await page.getByRole("button", { name: /^apply$/i }).click();
    await expect(page.getByText(/^resolved$/i)).toBeVisible();
  });

  test("an admin closes the bug", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);
    await page.goto(`/bugs/${bugAId}`);

    await page.getByLabel(/new status/i).selectOption("closed");
    await page.getByRole("button", { name: /^apply$/i }).click();
    await expect(page.getByText(/^closed$/i)).toBeVisible();
  });

  test("a viewer sees the bug read-only, with no mutation controls", async ({ page }) => {
    await signIn(page, VIEWER_EMAIL);
    await page.goto(`/bugs/${bugAId}`);

    await expect(page.getByRole("heading", { name: "App crashes on save" })).toBeVisible();
    await expect(page.getByRole("form", { name: /edit bug/i })).toHaveCount(0);
    await expect(page.getByLabel(/new status/i)).toHaveCount(0);
    await expect(page.getByText(/^archive bug$/i)).toHaveCount(0);
    // Watching is self-service and available to every member, viewer included.
    await expect(page.getByRole("button", { name: /^watch$/i })).toBeVisible();
  });

  test("the reporter reopens their own closed bug", async ({ page }) => {
    await signIn(page, REPORTER_EMAIL);
    await page.goto(`/bugs/${bugAId}`);

    // Reopen is the only transition a reporter may apply, and only on a
    // bug they reported themselves — the select should offer exactly that.
    const statusSelect = page.getByLabel(/new status/i);
    await expect(statusSelect).toBeVisible();
    await statusSelect.selectOption("reopened");
    await page.getByRole("button", { name: /^apply$/i }).click();
    await expect(page.getByText(/^reopened$/i)).toBeVisible();
  });

  test("an admin adds and removes a tag", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);
    await page.goto(`/bugs/${bugAId}`);

    await page.getByLabel(/new tag/i).fill("regression");
    // Scoped to the "Add tag" form — an unscoped "Add" button matches both
    // this form's submit and the "Add relationship" form's submit.
    await page.getByRole("form", { name: /add tag/i }).getByRole("button", { name: /^add$/i }).click();
    await expect(page.getByText("regression")).toBeVisible();

    await page.getByRole("button", { name: /remove tag regression/i }).click();
    await expect(page.getByText("regression")).toHaveCount(0);
  });

  test("an admin archives the bug, then restores it", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);
    await page.goto(`/bugs/${bugAId}`);

    await page.getByRole("button", { name: /^archive bug$/i }).click();
    await page.getByRole("button", { name: /^confirm$/i }).click();
    await expect(page.getByText(/archived and cannot be edited/i)).toBeVisible();

    await page.getByRole("button", { name: /restore bug/i }).click();
    await expect(page.getByRole("form", { name: /edit bug/i })).toBeVisible();
  });

  test("an admin marks a fresh bug as a duplicate of another", async ({ page }) => {
    const originalId = await createBug(page, "Original: export button missing");
    const duplicateId = await createBug(page, "Duplicate: export button missing");

    await signIn(page, ADMIN_EMAIL);
    await page.goto(`/bugs/${originalId}`);
    const originalKey = (await page.locator("span.font-mono").first().textContent())?.trim() ?? "";
    expect(originalKey).not.toBe("");

    await page.goto(`/bugs/${duplicateId}`);
    await page.getByLabel(/new status/i).selectOption("duplicate");
    await page.getByLabel(/duplicate of/i).fill(originalKey);
    await page.getByRole("button", { name: /^apply$/i }).click();

    await expect(page.getByText(/^duplicate$/i)).toBeVisible();
    await expect(page.getByText(new RegExp(`Duplicate of.*${originalKey}`))).toBeVisible();
  });

  test("a concurrent edit surfaces a version conflict, not a silent overwrite", async ({ browser }) => {
    const contextA = await browser.newContext();
    const contextB = await browser.newContext();
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    await signIn(pageA, ADMIN_EMAIL);
    await signIn(pageB, ADMIN_EMAIL);
    await pageA.goto(`/bugs/${bugAId}`);
    await pageB.goto(`/bugs/${bugAId}`);
    await expect(pageA.getByRole("form", { name: /edit bug/i })).toBeVisible();
    await expect(pageB.getByRole("form", { name: /edit bug/i })).toBeVisible();

    await pageA.getByLabel(/^title$/i).fill("Edited from tab A");
    await pageA.getByRole("button", { name: /save changes/i }).click();
    await expect(pageA.getByRole("heading", { name: "Edited from tab A" })).toBeVisible();

    // pageB still holds the pre-edit version — its save must be rejected,
    // not silently overwrite tab A's change.
    await pageB.getByLabel(/^title$/i).fill("Edited from tab B");
    await pageB.getByRole("button", { name: /save changes/i }).click();
    await expect(pageB.getByText(/changed by someone else since you loaded it/i)).toBeVisible();

    await pageB.getByRole("button", { name: /reload latest version/i }).click();
    await expect(pageB.getByRole("heading", { name: "Edited from tab A" })).toBeVisible();

    await contextA.close();
    await contextB.close();
  });
});
