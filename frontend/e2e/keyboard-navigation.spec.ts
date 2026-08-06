import { expect, test, type Page } from "@playwright/test";

// Reuses the bug-e2e fixture (seeded once, idempotently, by global-setup.ts)
// — namespaced independently of accessibility.spec.ts's analytics-e2e
// fixture and every other spec file's fixtures, so this file has no
// dependency on execution order.
const ADMIN_EMAIL = "bug-e2e-admin@example.com";
const REPORTER_EMAIL = "bug-e2e-reporter@example.com";
const PASSWORD = "BugE2EPass123!";
const PROJECT_LABEL = "BEP — Bug E2E Project";

// Keyboard-only sign-in: Tab between fields and submit with Enter, never a
// mouse click — this is the sign-in path itself under test in the first
// case below, and a plain helper (using .fill()/.click(), which is
// equivalent for a user who *can* use a mouse) for every other case that
// merely needs to be signed in before testing something else.
async function signIn(page: Page, email: string) {
  await page.goto("/sign-in");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await expect(page).toHaveURL("/");
}

test.describe("keyboard-only navigation", () => {
  test("signs in using only the keyboard", async ({ page }) => {
    await page.goto("/sign-in");
    await page.getByLabel(/email/i).click();
    await page.keyboard.type(ADMIN_EMAIL);
    await page.keyboard.press("Tab");
    await expect(page.getByLabel(/password/i)).toBeFocused();
    await page.keyboard.type(PASSWORD);
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL("/");
  });

  test("the skip link is the first stop and moves focus to main content", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);
    await page.goto("/bugs");
    await expect(page.getByRole("table")).toBeVisible();

    // A fresh navigation has no active element yet, so the skip link must
    // be the first thing reachable *within the app's own content* — not
    // buried after the whole header. In this dev-server environment
    // specifically (not production), Next.js's own dev-tools overlay
    // (<nextjs-portal>, a shadow-DOM custom element with several internal
    // tab stops of its own — document.activeElement reports the host
    // element itself for all of them) inserts itself before any app
    // content and is absent from production builds entirely, so it's
    // tabbed past here rather than counted against the app.
    for (let attempt = 0; attempt < 10; attempt++) {
      await page.keyboard.press("Tab");
      const isDevToolsOverlay = await page.evaluate(
        () => document.activeElement?.tagName.toLowerCase() === "nextjs-portal",
      );
      if (!isDevToolsOverlay) break;
    }
    await expect(page.getByRole("link", { name: /skip to main content/i })).toBeFocused();

    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
  });

  test("creates a bug using only the keyboard", async ({ page }) => {
    await signIn(page, REPORTER_EMAIL);
    await page.goto("/bugs/new");
    await expect(page.getByRole("form", { name: /create bug/i })).toBeVisible();

    await page.getByLabel(/^project$/i).focus();
    await page.getByLabel(/^project$/i).selectOption({ label: PROJECT_LABEL });
    await page.keyboard.press("Tab");
    await expect(page.getByLabel(/^title$/i)).toBeFocused();
    await page.keyboard.type("E2E keyboard-only bug creation");
    await page.getByRole("button", { name: /^create bug$/i }).focus();
    await page.keyboard.press("Enter");

    await expect(page.getByRole("heading", { name: "E2E keyboard-only bug creation" })).toBeVisible({
      timeout: 15000,
    });
  });

  test("opens and closes the notification dropdown with the keyboard, returning focus to the trigger", async ({
    page,
  }) => {
    await signIn(page, ADMIN_EMAIL);

    const trigger = page.getByRole("button", { name: /^notifications$/i });
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByLabel(/recent notifications/i)).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByLabel(/recent notifications/i)).not.toBeVisible();
    await expect(trigger).toBeFocused();
  });

  test("cancels a destructive dialog with the keyboard and returns focus to its trigger", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);
    await page.goto("/bugs/new");
    await page.getByLabel(/^project$/i).selectOption({ label: PROJECT_LABEL });
    await page.getByLabel(/^title$/i).fill("E2E keyboard archive-cancel bug");
    await page.getByRole("button", { name: /^create bug$/i }).click();
    await expect(page.getByRole("heading", { name: "E2E keyboard archive-cancel bug" })).toBeVisible({
      timeout: 15000,
    });

    const archiveTrigger = page.getByRole("button", { name: /^archive bug$/i });
    await archiveTrigger.focus();
    await page.keyboard.press("Enter");

    const dialog = page.getByRole("alertdialog", { name: /confirm archive bug/i });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(archiveTrigger).toBeFocused();
    // Cancelling must not have archived it.
    await expect(page.getByText(/this bug is archived/i)).not.toBeVisible();
  });
});
