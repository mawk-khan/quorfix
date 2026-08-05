import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { waitForNotificationsPageToContain } from "./notification-helpers";

// Reuses the same namespaced, idempotent fixture as bug-lifecycle.spec.ts and
// watcher-notifications.spec.ts (apps/core/management/commands/
// seed_e2e_bug_fixture.py), seeded once by global-setup.ts before any spec
// runs. This file creates its own bug in its own test.describe.serial block,
// so it is independent of every other spec file and of run order — nothing
// here depends on what bug-lifecycle.spec.ts or watcher-notifications.spec.ts
// created, or whether they ran at all.
const ADMIN_EMAIL = "bug-e2e-admin@example.com";
const DEVELOPER_EMAIL = "bug-e2e-developer@example.com";
const REPORTER_EMAIL = "bug-e2e-reporter@example.com";
const VIEWER_EMAIL = "bug-e2e-viewer@example.com";
const PASSWORD = "BugE2EPass123!";
const PROJECT_LABEL = "BEP — Bug E2E Project";

const FIXTURES_DIR = path.join(__dirname, "fixtures", "collaboration");
const SAMPLE_PNG = path.join(FIXTURES_DIR, "sample.png");

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
  const key = (await page.locator("p.font-mono").first().textContent())?.trim() ?? "";
  expect(key).not.toBe("");
  return { id, key };
}

let bugId = "";
let bugKey = "";

test.describe.serial("collaboration lifecycle: comments, mentions, and attachments", () => {
  test("a reporter creates a bug and posts a comment", async ({ page }) => {
    const bug = await createBug(page, "Collaboration lifecycle: discussion needed");
    bugId = bug.id;
    bugKey = bug.key;

    await page.getByLabel(/add a comment/i).fill("I can reproduce this every time on staging.");
    await page.getByRole("button", { name: /post comment/i }).click();

    await expect(page.getByText("I can reproduce this every time on staging.")).toBeVisible();
  });

  test("an admin mentions the developer using the mention picker", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);
    await page.goto(`/bugs/${bugId}`);

    const commentBox = page.getByLabel(/add a comment/i);
    await commentBox.pressSequentially("Hey @Dev");
    const mentionListbox = page.getByRole("listbox", { name: /mention suggestions/i });
    await expect(mentionListbox).toBeVisible();
    // Scoped to the mention listbox specifically — an unscoped
    // getByRole("option", ...) can also match a native <select>'s <option>
    // elements elsewhere on the page (e.g. the assignee dropdown), which
    // share the same accessible "option" role but aren't independently
    // clickable the way this custom listbox's options are.
    await mentionListbox.getByRole("option", { name: /developer/i }).first().click();
    await commentBox.pressSequentially(" can you take a look?");
    await page.getByRole("button", { name: /post comment/i }).click();

    // The structured mention token renders as a styled "@Name" span, not the
    // raw @[Name](mention:<uuid>) source.
    await expect(page.getByTestId("mention-token")).toBeVisible();
    await expect(page.getByText(/mention:/)).toHaveCount(0);
  });

  test("the mentioned developer receives exactly one mention notification for this bug", async ({ page }) => {
    await signIn(page, DEVELOPER_EMAIL);
    await waitForNotificationsPageToContain(page, new RegExp(bugKey), 20_000, "/notifications?event_type=mentioned");

    const mentionedRows = page.locator("li", { hasText: bugKey });
    await expect(mentionedRows).toHaveCount(1);
  });

  test("the reporter edits their own comment within the edit window", async ({ page }) => {
    await signIn(page, REPORTER_EMAIL);
    await page.goto(`/bugs/${bugId}`);

    await page
      .getByTestId("comment-item")
      .filter({ hasText: "I can reproduce this every time on staging." })
      .getByRole("button", { name: /^edit$/i })
      .click();
    const editBox = page.getByLabel(/edit comment/i);
    await editBox.fill("I can reproduce this every time on staging — attaching a screenshot.");
    await page.getByRole("button", { name: /^save$/i }).click();

    await expect(page.getByText("I can reproduce this every time on staging — attaching a screenshot.")).toBeVisible();
    await expect(page.getByText("(edited)")).toBeVisible();
  });

  test("the developer uploads an attachment and sees it complete", async ({ page }) => {
    await signIn(page, DEVELOPER_EMAIL);
    await page.goto(`/bugs/${bugId}`);

    await page.getByLabel(/upload attachment/i).setInputFiles(SAMPLE_PNG);
    // A tiny local fixture file uploads fast enough that the in-flight row
    // can reach "Uploaded" and then be dropped (once the persisted
    // attachment shows up in the real list below it) before an assertion on
    // the transient row text would reliably observe it — the durable,
    // meaningful success signal is the persisted row appearing.
    await expect(page.getByTestId("attachment-row").filter({ hasText: "sample.png" })).toBeVisible({ timeout: 15000 });
  });

  test("the developer downloads the attachment", async ({ page }) => {
    await signIn(page, DEVELOPER_EMAIL);
    await page.goto(`/bugs/${bugId}`);

    const downloadPromise = page.waitForEvent("download");
    await page
      .getByTestId("attachment-row")
      .filter({ hasText: "sample.png" })
      .getByRole("button", { name: /^download$/i })
      .click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("sample.png");
  });

  test("a viewer can read the discussion and download the attachment, but cannot comment or upload", async ({ page }) => {
    await signIn(page, VIEWER_EMAIL);
    await page.goto(`/bugs/${bugId}`);

    await expect(page.getByText(/attaching a screenshot/i)).toBeVisible();
    await expect(page.getByLabel(/add a comment/i)).toHaveCount(0);
    await expect(page.getByLabel(/upload attachment/i)).toHaveCount(0);

    const downloadPromise = page.waitForEvent("download");
    await page
      .getByTestId("attachment-row")
      .filter({ hasText: "sample.png" })
      .getByRole("button", { name: /^download$/i })
      .click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("sample.png");
  });

  test("the uploader removes their own attachment while the bug is still mutable", async ({ page }) => {
    await signIn(page, DEVELOPER_EMAIL);
    await page.goto(`/bugs/${bugId}`);

    await page
      .getByTestId("attachment-row")
      .filter({ hasText: "sample.png" })
      .getByRole("button", { name: /^remove$/i })
      .click();
    await page.getByRole("button", { name: /confirm remove/i }).click();

    await expect(page.getByTestId("attachment-row").filter({ hasText: "sample.png" })).toHaveCount(0);
  });

  test("activity entries reflect the comment, mention, edit, and attachment actions", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);
    await page.goto(`/bugs/${bugId}`);

    await expect(page.getByRole("heading", { name: /^activity$/i })).toBeVisible();
    await expect(page.getByText(/added a comment/i).first()).toBeVisible();
    await expect(page.getByText(/mentioned a teammate/i)).toBeVisible();
    await expect(page.getByText(/edited a comment/i)).toBeVisible();
    await expect(page.getByText(/added an attachment/i)).toBeVisible();
    await expect(page.getByText(/removed an attachment/i)).toBeVisible();
  });

  test("an administrator can redact a comment after the bug is archived", async ({ page }) => {
    await signIn(page, ADMIN_EMAIL);
    await page.goto(`/bugs/${bugId}`);

    await page.getByRole("button", { name: /^archive bug$/i }).click();
    await page.getByRole("button", { name: /^confirm$/i }).click();
    await expect(page.getByText(/archived and cannot be edited/i)).toBeVisible();

    // Moderation stays available on an archived bug — the read-only comment
    // form message is shown instead of a compose form, but existing comment
    // actions (redact) remain.
    await expect(page.getByText(/archived, so new comments cannot be added/i)).toBeVisible();
    await page
      .getByTestId("comment-item")
      .filter({ hasText: "attaching a screenshot" })
      .getByRole("button", { name: /^redact$/i })
      .click();
    await expect(page.getByText(/moderation record will remain/i)).toBeVisible();
    await page.getByRole("button", { name: /confirm redact/i }).click();

    await expect(page.getByTestId("comment-placeholder").filter({ hasText: /redacted by an administrator/i })).toBeVisible();
    await expect(page.getByText(/attaching a screenshot/i)).toHaveCount(0);
  });
});
