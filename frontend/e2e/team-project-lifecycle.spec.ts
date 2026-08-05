import { expect, test, type Page } from "@playwright/test";

// Filename ordering matters here: Playwright Test runs e2e spec files in
// the sorted order it discovers them (confirmed via `playwright test
// --list`), and first-run setup can only succeed once per database (see
// SetupLock in apps/organizations, and global-setup.ts). This file's name
// is deliberately chosen to sort after team-journey.spec.ts so it can rely
// on that file having already completed first-run setup — creating the
// "Acme" organization and its admin account — rather than repeating setup
// itself, which would conflict with team-journey.spec.ts's own assumption
// that it is the one spec performing it.
const ADMIN_EMAIL = "admin@example.com";
const ADMIN_PASSWORD = "Str0ngPassw0rd!";
const VIEWER_EMAIL = "project-viewer@example.com";
const VIEWER_PASSWORD = "AnotherStr0ngPass!";

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/sign-in");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await expect(page).toHaveURL("/");
}

let projectId = "";
let inviteUrl = "";

// Serial for the same reason as team-journey.spec.ts: this is one
// continuous journey (create -> search -> edit -> archive -> restore)
// against project state each step builds on, not independent cases.
test.describe.serial("project lifecycle", () => {
  test("an administrator creates a project", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/projects");
    // Generous timeout: this is the dev server's first-ever compile of the
    // /projects route (on-demand compilation), which can take longer than
    // Playwright's default 5s assertion timeout. Later navigations to
    // already-compiled routes don't need this.
    await expect(page.getByRole("heading", { name: /^projects$/i })).toBeVisible({
      timeout: 15000,
    });

    await page.getByRole("link", { name: /new project/i }).click();
    await page.getByLabel(/^name$/i).fill("Engine");
    await page.getByLabel(/^key$/i).fill("eng");
    await page.getByRole("button", { name: /create project/i }).click();

    // Same first-compile allowance for the dynamic /projects/[id] route.
    await expect(page.getByRole("heading", { name: "Engine" })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("ENG", { exact: true })).toBeVisible();

    projectId = new URL(page.url()).pathname.split("/").filter(Boolean).pop() ?? "";
    expect(projectId).not.toBe("");
  });

  test("the project is searchable by key from the list", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/projects");
    await page.getByLabel(/^search$/i).fill("eng");

    await expect(page.getByRole("link", { name: "Engine" })).toBeVisible();
  });

  test("an administrator edits the project name", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto(`/projects/${projectId}`);

    await page.getByLabel(/^name$/i).fill("Engine Team");
    await page.getByRole("button", { name: /save changes/i }).click();

    await expect(page.getByRole("heading", { name: "Engine Team" })).toBeVisible();
  });

  test("an administrator invites a teammate who can view but not edit the project", async ({
    page,
  }) => {
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/team");

    await page.getByLabel(/^email$/i).fill(VIEWER_EMAIL);
    await page.getByLabel(/^role$/i).selectOption("viewer");
    await page.getByRole("button", { name: /^invite$/i }).click();

    const link = page.getByRole("link", { name: /invitations\// });
    await expect(link).toBeVisible();
    inviteUrl = (await link.getAttribute("href")) ?? "";
    expect(inviteUrl).toContain("/invitations/");
  });

  test("the invited teammate accepts and lands signed in", async ({ page }) => {
    const url = new URL(inviteUrl);
    await page.goto(url.pathname + url.search);
    await page.getByLabel(/password/i).fill(VIEWER_PASSWORD);
    await page.getByRole("button", { name: /accept invitation/i }).click();

    await expect(page).toHaveURL("/");
  });

  test("the viewer can see the project but has no mutation controls", async ({ page }) => {
    await signIn(page, VIEWER_EMAIL, VIEWER_PASSWORD);
    await page.goto(`/projects/${projectId}`);

    await expect(page.getByRole("heading", { name: "Engine Team" })).toBeVisible();
    await expect(page.getByRole("form", { name: /edit project/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /archive project/i })).toHaveCount(0);
  });

  test("archiving hides the project from the default list but keeps it under the archived filter", async ({
    page,
  }) => {
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto(`/projects/${projectId}`);

    await page.getByRole("button", { name: /^archive project$/i }).click();
    await page.getByRole("button", { name: /^confirm$/i }).click();
    await expect(page.getByText(/^archived$/i)).toBeVisible();

    await page.goto("/projects");
    await expect(page.getByRole("link", { name: "Engine Team" })).toHaveCount(0);

    await page.getByLabel(/^status$/i).selectOption("true");
    await expect(page.getByRole("link", { name: "Engine Team" })).toBeVisible();
  });

  test("an archived project cannot be edited until it is restored", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto(`/projects/${projectId}`);

    await expect(page.getByRole("form", { name: /edit project/i })).toHaveCount(0);
    await page.getByRole("button", { name: /restore project/i }).click();

    await expect(page.getByRole("form", { name: /edit project/i })).toBeVisible();
    await expect(page.getByText(/^archived$/i)).toHaveCount(0);
  });
});
