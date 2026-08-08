import { expect, test, type Page } from "@playwright/test";

import { apiPost, findMemberByEmail, waitForNotificationsPageToContain } from "./notification-helpers";

// Deliberately reuses apps/core/management/commands/seed_e2e_bug_fixture.py's
// "Bug E2E Org" fixture — the same one e2e/bug-lifecycle.spec.ts uses —
// rather than relying on team-journey.spec.ts's first-run setup. That
// fixture is namespaced and idempotent, seeded once by global-setup.ts
// before any spec runs, so this file never depends on which other spec
// files ran or in what order. Every test below also creates its own bug,
// so tests within this file are independent of each other too.
const ADMIN_EMAIL = "bug-e2e-admin@example.com";
const DEVELOPER_EMAIL = "bug-e2e-developer@example.com";
const DEVELOPER_LABEL = `E2E Developer (${DEVELOPER_EMAIL})`;
const QA_EMAIL = "bug-e2e-qa@example.com";
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

async function watchBug(page: Page, email: string, bugId: string) {
  await signIn(page, email);
  await page.goto(`/bugs/${bugId}`);
  await page.getByRole("button", { name: /^watch$/i }).click();
  await expect(page.getByRole("button", { name: /^unwatch$/i })).toBeVisible();
}

async function postComment(page: Page, bugId: string, body: string) {
  await apiPost(page, `/api/bugs/${bugId}/comments/`, { body });
}

test("a watcher receives a comment_added notification when someone else comments", async ({
  page,
  browser,
}) => {
  const bug = await createBug(page, "Watcher notification: comment added");
  await watchBug(page, QA_EMAIL, bug.id);

  const actorContext = await browser.newContext();
  const actorPage = await actorContext.newPage();
  await signIn(actorPage, ADMIN_EMAIL);
  await postComment(actorPage, bug.id, "Looks like a real bug, thanks for reporting.");
  await actorContext.close();

  await signIn(page, QA_EMAIL);
  await waitForNotificationsPageToContain(page, new RegExp(`${bug.key}.*commented|commented.*${bug.key}`, "s"));
});

test("a mentioned user receives one mention notification, not a duplicate comment_added", async ({
  page,
  browser,
}) => {
  const bug = await createBug(page, "Watcher notification: mention precedence");
  // developer also watches, proving mention precedence holds even though
  // they'd otherwise qualify for comment_added too.
  await watchBug(page, DEVELOPER_EMAIL, bug.id);

  const actorContext = await browser.newContext();
  const actorPage = await actorContext.newPage();
  await signIn(actorPage, ADMIN_EMAIL);
  const developer = await findMemberByEmail(actorPage, DEVELOPER_EMAIL);
  await postComment(actorPage, bug.id, `Hey @[Dev](mention:${developer.user.id}) can you take a look?`);
  await actorContext.close();

  await signIn(page, DEVELOPER_EMAIL);
  await waitForNotificationsPageToContain(page, new RegExp(`${bug.key}`));

  // Scoped to this test's own bug (by key) throughout — a shared,
  // non-flushed dev database can carry other runs' notifications with
  // similar text, so asserting on the row for this specific bug is what
  // actually proves the precedence rule, not just "some mention exists
  // somewhere".
  await page.goto(`/notifications?event_type=mentioned`);
  const mentionedRow = page.locator("li", { hasText: bug.key });
  await expect(mentionedRow).toHaveCount(1);
  await expect(mentionedRow.getByText(/mentioned you/i)).toBeVisible();

  await page.goto(`/notifications?event_type=comment_added`);
  await expect(page.locator("li", { hasText: bug.key })).toHaveCount(0);
});

test("marking a notification read decreases the unread count", async ({ page, browser }) => {
  const bug = await createBug(page, "Watcher notification: mark read updates count");
  await watchBug(page, QA_EMAIL, bug.id);

  const actorContext = await browser.newContext();
  const actorPage = await actorContext.newPage();
  await signIn(actorPage, ADMIN_EMAIL);
  await postComment(actorPage, bug.id, "Confirmed on my end too.");
  await actorContext.close();

  await signIn(page, QA_EMAIL);
  await waitForNotificationsPageToContain(page, new RegExp(bug.key));

  await page.goto("/bugs");
  const bellButton = page.getByRole("button", { name: /notifications, \d+ unread/i });
  await expect(bellButton).toBeVisible({ timeout: 15000 });
  const before = Number((await bellButton.getAttribute("aria-label"))?.match(/(\d+)/)?.[1] ?? "0");
  expect(before).toBeGreaterThan(0);

  await page.goto("/notifications");
  await page.getByRole("button", { name: /^mark read$/i }).first().click();

  await page.goto("/bugs");
  await expect
    .poll(async () => {
      const label = await page.getByRole("button", { name: /notifications/i }).getAttribute("aria-label");
      return Number(label?.match(/(\d+)/)?.[1] ?? "0");
    })
    .toBeLessThan(before);
});

test("the assignee receives a bug_assigned notification", async ({ page }) => {
  const bug = await createBug(page, "Watcher notification: assignment");

  await signIn(page, ADMIN_EMAIL);
  await page.goto(`/bugs/${bug.id}`);
  await page.getByLabel(/^assignee$/i).selectOption({ label: DEVELOPER_LABEL });
  await page.getByRole("button", { name: /update assignee/i }).click();
  await expect(page.getByTestId("current-assignee")).toHaveText(/E2E Developer/);

  await signIn(page, DEVELOPER_EMAIL);
  await page.goto(`/notifications?event_type=bug_assigned`);
  await waitForNotificationsPageToContain(page, /assigned you/i);
  await expect(page.getByText(bug.key, { exact: false })).toBeVisible();
});

test("watchers receive a bug_reopened notification, distinct from status_changed", async ({ page }) => {
  // Deliberately does not contain the word "reopened" in the title — the
  // wait below polls for the bug's key, and a title containing "reopened"
  // would make a plain /reopened/i text search match prematurely against an
  // earlier (correct, but different) status_changed notification for this
  // same bug, before the real bug_reopened notification has actually landed.
  const bug = await createBug(page, "Watcher notification: full transition cycle");
  await watchBug(page, QA_EMAIL, bug.id);

  await signIn(page, ADMIN_EMAIL);
  await page.goto(`/bugs/${bug.id}`);

  await page.getByLabel(/^assignee$/i).selectOption({ label: DEVELOPER_LABEL });
  await page.getByRole("button", { name: /update assignee/i }).click();
  await expect(page.getByTestId("current-assignee")).toHaveText(/E2E Developer/);

  await page.getByLabel(/new status/i).selectOption("assigned");
  await page.getByRole("button", { name: /^apply$/i }).click();
  await expect(page.getByText(/^assigned$/i)).toBeVisible();

  await page.getByLabel(/new status/i).selectOption("in_progress");
  await page.getByRole("button", { name: /^apply$/i }).click();
  await expect(page.getByText(/in progress/i)).toBeVisible();

  await page.getByLabel(/new status/i).selectOption("resolved");
  await page.getByRole("button", { name: /^apply$/i }).click();
  await expect(page.getByText(/^resolved$/i)).toBeVisible();

  await page.getByLabel(/new status/i).selectOption("reopened");
  await page.getByRole("button", { name: /^apply$/i }).click();
  await expect(page.getByText(/^reopened$/i)).toBeVisible();

  await signIn(page, QA_EMAIL);
  // Polls the filtered event_type=bug_reopened view directly rather than
  // the unfiltered page — the earlier status_changed notifications for this
  // same bug (assigned/in_progress/resolved) would otherwise satisfy a
  // generic "does the page contain this bug's key" check well before the
  // real bug_reopened notification has landed, under concurrent Celery task
  // processing.
  await waitForNotificationsPageToContain(page, new RegExp(bug.key), 20_000, "/notifications?event_type=bug_reopened");

  // Exactly one bug_reopened row for this bug — never emitted alongside a
  // status_changed row for the same transition (apps.bugs.services.
  // transition_bug dispatches one or the other, never both).
  const reopenedRows = page.locator("li", { hasText: bug.key });
  await expect(reopenedRows).toHaveCount(1);
});
