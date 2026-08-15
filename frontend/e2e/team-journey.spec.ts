import { expect, test, type Page } from "@playwright/test";

const ADMIN_EMAIL = "admin@example.com";
const ADMIN_PASSWORD = "Str0ngPassw0rd!";
const DEV_EMAIL = "dev@example.com";
const DEV_PASSWORD = "AnotherStr0ngPass!";

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/sign-in");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await expect(page).toHaveURL("/");
}

let inviteUrl = "";

// Serial: this is one continuous journey against a single fresh instance,
// not independent cases — first-run setup can only succeed once per
// database (see global-setup.ts), and later steps depend on state earlier
// steps create (the organization, the admin account, the invite link).
// Each test() still gets its own isolated browser context/cookies per
// Playwright's default, so any test needing an authenticated session signs
// in explicitly rather than assuming a previous test's session carries over.
test.describe.serial("first-run setup through team management", () => {
  test("a fresh instance requires setup", async ({ page }) => {
    await page.goto("/setup");
    await expect(page.getByRole("heading", { name: /set up quorfix/i })).toBeVisible();
  });

  test("completing setup creates the org and signs the admin in", async ({ page }) => {
    await page.goto("/setup");
    await page.getByLabel(/organization name/i).fill("Acme");
    await page.getByLabel(/your email/i).fill(ADMIN_EMAIL);
    await page.getByLabel(/^password$/i).fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: /create administrator account/i }).click();

    await expect(page).toHaveURL("/");
    await expect(page.getByText(new RegExp(`signed in as ${ADMIN_EMAIL}`, "i"))).toBeVisible();
  });

  test("visiting /setup again redirects to sign-in", async ({ page }) => {
    await page.goto("/setup");
    await expect(page).toHaveURL("/sign-in");
  });

  test("admin invites a teammate and gets a one-time shareable link", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/team");

    await page.getByLabel(/^email$/i).fill(DEV_EMAIL);
    await page.getByLabel(/^role$/i).selectOption("developer");
    await page.getByRole("button", { name: /^invite$/i }).click();

    const link = page.getByRole("link", { name: /invitations\// });
    await expect(link).toBeVisible();
    inviteUrl = (await link.getAttribute("href")) ?? "";
    expect(inviteUrl).toContain("/invitations/");
  });

  test("the invited teammate accepts and lands signed in", async ({ page }) => {
    const url = new URL(inviteUrl);
    await page.goto(url.pathname + url.search);

    await expect(page.getByRole("heading", { name: /join acme/i })).toBeVisible();
    await page.getByLabel(/password/i).fill(DEV_PASSWORD);
    await page.getByRole("button", { name: /accept invitation/i }).click();

    await expect(page).toHaveURL("/");
    await expect(page.getByText(new RegExp(`signed in as ${DEV_EMAIL}`, "i"))).toBeVisible();
  });

  test("the developer cannot see admin-only team controls", async ({ page }) => {
    await signIn(page, DEV_EMAIL, DEV_PASSWORD);
    await page.goto("/team");

    await expect(page.getByRole("cell", { name: DEV_EMAIL })).toBeVisible();
    await expect(page.getByRole("form", { name: /invite a member/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /remove/i })).toHaveCount(0);
  });

  test("the admin can change the developer's role and then remove them", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/team");

    const roleSelect = page.getByLabel(new RegExp(`role for ${DEV_EMAIL}`, "i"));
    await roleSelect.selectOption("qa");
    await expect(roleSelect).toHaveValue("qa");

    await page
      .locator("tr", { hasText: DEV_EMAIL })
      .getByRole("button", { name: /remove/i })
      .click();
    await expect(page.getByText(DEV_EMAIL)).toHaveCount(0);
  });
});
