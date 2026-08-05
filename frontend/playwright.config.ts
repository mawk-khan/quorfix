import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // Every spec shares one backend instance with global mutable state (a
  // single organization, a one-time setup lock) — parallel workers would
  // stomp on each other's state, so this suite runs serially.
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  // CI additionally gets an HTML report — a self-contained artifact the
  // GitHub Actions job uploads on every run (see .github/workflows/e2e.yml)
  // so a failure can be inspected without re-running the suite locally.
  // Local runs keep the plain "list" output only.
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
