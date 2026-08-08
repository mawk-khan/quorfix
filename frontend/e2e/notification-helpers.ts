import { expect, type Page } from "@playwright/test";

// Shared by every notification e2e spec — there is no comment-thread UI yet
// (Chunk 1 was backend-only), so creating a comment or a mention has no UI
// path at all and must go through the API directly, with the same
// CSRF-cookie convention frontend/src/lib/api/client.ts already uses.

async function readCsrfToken(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((cookie) => cookie.name === "csrftoken");
  if (!csrf) throw new Error("csrftoken cookie not found — is the caller signed in?");
  return csrf.value;
}

export async function apiPost<T>(page: Page, path: string, data: unknown): Promise<T> {
  const csrfToken = await readCsrfToken(page);
  const response = await page.request.post(path, { data, headers: { "X-CSRFToken": csrfToken } });
  if (!response.ok()) {
    throw new Error(`POST ${path} failed with ${response.status()}: ${await response.text()}`);
  }
  return response.json();
}

export async function apiGet<T>(page: Page, path: string): Promise<T> {
  const response = await page.request.get(path);
  if (!response.ok()) {
    throw new Error(`GET ${path} failed with ${response.status()}: ${await response.text()}`);
  }
  return response.json();
}

export async function apiPatch<T>(page: Page, path: string, data: unknown): Promise<T> {
  const csrfToken = await readCsrfToken(page);
  const response = await page.request.patch(path, { data, headers: { "X-CSRFToken": csrfToken } });
  if (!response.ok()) {
    throw new Error(`PATCH ${path} failed with ${response.status()}: ${await response.text()}`);
  }
  return response.json();
}

// Preference tests mutate real, persistent rows for the shared e2e personas
// — resetting to a known state at the start of each test (rather than
// assuming "missing row means enabled" holds because nothing has touched it
// yet) means this file stays safely re-runnable against the same database
// without requiring a flush between runs, on top of already being
// independent of other spec files.
export async function resetPreferenceToEnabled(page: Page, eventType: string) {
  await apiPatch(page, `/api/notifications/preferences/${eventType}/`, { email_enabled: true });
}

export interface MemberRef {
  id: string;
  user: { id: string; email: string; first_name: string; last_name: string };
}

export async function findMemberByEmail(page: Page, email: string): Promise<MemberRef> {
  const body = await apiGet<{ results: MemberRef[] }>(page, "/api/members/");
  const member = body.results.find((m) => m.user.email === email);
  if (!member) throw new Error(`No member found with email ${email}`);
  return member;
}

export function mentionToken(displayName: string, userId: string): string {
  return `@[${displayName}](mention:${userId})`;
}

// Notifications are delivered asynchronously through a real Celery worker
// consuming the real Redis broker in this environment — config.settings.
// development is never CELERY_TASK_ALWAYS_EAGER, matching production, and
// .github/workflows/e2e.yml's "Start Celery worker" step is what actually
// processes the queue in CI (there is no docker compose there, so nothing
// else would). Never assume a dispatched event has already produced a
// Notification row by the time the next line runs — poll observable state
// on a bounded timeout instead of an arbitrary sleep.
export async function waitForNotificationsPageToContain(
  page: Page,
  pattern: RegExp,
  timeoutMs = 20_000,
  path = "/notifications",
) {
  await expect
    .poll(
      async () => {
        await page.goto(path);
        // page.goto() resolves once the document has loaded — well before
        // the client-side TanStack Query fetch it triggers has resolved.
        // Reading innerText immediately after goto would almost always
        // observe a loading placeholder rather than the fetch's result,
        // regardless of how many times this polls. Two separate loading
        // states exist here and both must clear: the session guard (a
        // literal "Loading…" paragraph) and the notifications list query
        // itself, which renders as an aria-hidden, textless Skeleton — so
        // waiting for "Loading…" to detach says nothing about whether the
        // list query has resolved. networkidle covers both without coupling
        // this helper to either page's specific loading markup.
        await page
          .getByText("Loading…", { exact: true })
          .waitFor({ state: "detached", timeout: 5000 })
          .catch(() => {});
        await page.waitForLoadState("networkidle");
        const text = await page.locator("main").innerText();
        return pattern.test(text);
      },
      { timeout: timeoutMs, message: `Expected /notifications to eventually contain ${pattern}` },
    )
    .toBe(true);
}
