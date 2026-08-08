import { expect, test, type Page } from "@playwright/test";

import {
  apiPost,
  findMemberByEmail,
  resetPreferenceToEnabled,
  waitForNotificationsPageToContain,
} from "./notification-helpers";

const COMMUNITY_EVENT_TYPES = ["bug_assigned", "mentioned", "comment_added", "status_changed", "bug_reopened"];

// Same isolated, order-independent fixture as watcher-notifications.spec.ts
// and e2e/bug-lifecycle.spec.ts — see the comment there for why.
const ADMIN_EMAIL = "bug-e2e-admin@example.com";
const DEVELOPER_EMAIL = "bug-e2e-developer@example.com";
const REPORTER_EMAIL = "bug-e2e-reporter@example.com";
const PASSWORD = "BugE2EPass123!";
const PROJECT_LABEL = "BEP — Bug E2E Project";

async function signIn(page: Page, email: string) {
  await page.goto("/sign-in");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await expect(page).toHaveURL("/");
}

async function createBug(page: Page, title: string): Promise<{ id: string; key: string }> {
  await signIn(page, REPORTER_EMAIL);
  await page.goto("/bugs/new");
  await expect(page.getByRole("form", { name: /create bug/i })).toBeVisible({ timeout: 15000 });
  await page.getByLabel(/^project$/i).selectOption({ label: PROJECT_LABEL });
  await page.getByLabel(/^title$/i).fill(title);
  await page.getByRole("button", { name: /create bug/i }).click();

  await expect(page.getByRole("heading", { name: title })).toBeVisible({ timeout: 15000 });
  const id = new URL(page.url()).pathname.split("/").filter(Boolean).pop() ?? "";
  expect(id).not.toBe("");
  const key = (await page.locator("span.font-mono").first().textContent())?.trim() ?? "";
  expect(key).not.toBe("");
  return { id, key };
}

test("email preferences page shows all five Community event types, enabled by default", async ({ page }) => {
  await signIn(page, DEVELOPER_EMAIL);
  // Self-healing: other tests in this file toggle developer's preferences
  // off, and this file may be re-run against the same database without a
  // flush between runs — reset to a known state first rather than assuming
  // "no row yet" happens to still be true.
  for (const eventType of COMMUNITY_EVENT_TYPES) {
    await resetPreferenceToEnabled(page, eventType);
  }
  await page.goto("/notifications/preferences");

  await expect(page.getByRole("heading", { name: /email notification preferences/i })).toBeVisible();
  const checkboxes = page.getByRole("checkbox");
  await expect(checkboxes).toHaveCount(5);
  for (const checkbox of await checkboxes.all()) {
    await expect(checkbox).toBeChecked();
  }
});

test("disabling the mentioned email preference still leaves the in-app notification, with email disabled", async ({
  page,
  browser,
}) => {
  const bug = await createBug(page, "Preferences: mention with email disabled");

  await signIn(page, DEVELOPER_EMAIL);
  // Deterministic starting point regardless of what earlier runs left behind.
  await resetPreferenceToEnabled(page, "mentioned");
  await page.goto("/notifications/preferences");
  const mentionedToggle = page.getByLabel(/mentioned in a comment/i);
  // Not .uncheck() — this checkbox is purely server-state-controlled (no
  // optimistic update), so its checked attribute only actually flips once
  // the update mutation round-trips and the query refetches. .uncheck()
  // requires the click itself to change the state and fails immediately
  // otherwise; a plain click + an auto-retrying assertion correctly waits
  // for that eventual, network-driven state instead.
  await mentionedToggle.click();
  await expect(mentionedToggle).not.toBeChecked();
  // Round-trips through the API; reloading proves the server, not just
  // local component state, now reflects the change.
  await page.reload();
  await expect(page.getByLabel(/mentioned in a comment/i)).not.toBeChecked();

  const actorContext = await browser.newContext();
  const actorPage = await actorContext.newPage();
  await signIn(actorPage, ADMIN_EMAIL);
  const developer = await findMemberByEmail(actorPage, DEVELOPER_EMAIL);
  await apiPost(actorPage, `/api/bugs/${bug.id}/comments/`, {
    body: `Hey @[Dev](mention:${developer.user.id}) urgent!`,
  });
  await actorContext.close();

  await waitForNotificationsPageToContain(page, new RegExp(bug.key));

  // The in-app notification exists regardless of the email preference —
  // only email delivery is disabled. email_status is API-visible precisely
  // so this is externally verifiable, not just inferred.
  const response = await page.request.get("/api/notifications/?event_type=mentioned");
  const body = (await response.json()) as { results: { email_status: string; bug: { key: string } }[] };
  const match = body.results.find((row) => row.bug.key === bug.key);
  expect(match).toBeDefined();
  expect(match?.email_status).toBe("disabled");
});

test("a user can only ever change their own preferences", async ({ page, browser }) => {
  // Two independent browser contexts, two different signed-in users —
  // confirms the developer's preference change never touches the admin's.
  const devContext = await browser.newContext();
  const devPage = await devContext.newPage();
  await signIn(devPage, DEVELOPER_EMAIL);
  await resetPreferenceToEnabled(devPage, "status_changed");
  await devPage.goto("/notifications/preferences");
  await devPage.getByLabel(/bug you watch changes status/i).click();
  await expect(devPage.getByLabel(/bug you watch changes status/i)).not.toBeChecked();
  await devContext.close();

  await signIn(page, ADMIN_EMAIL);
  await resetPreferenceToEnabled(page, "status_changed");
  await page.goto("/notifications/preferences");
  await expect(page.getByLabel(/bug you watch changes status/i)).toBeChecked();
});
