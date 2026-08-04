import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // Every spec shares one backend instance with global mutable state (a
  // single organization, a one-time setup lock) — parallel workers would
  // stomp on each other's state, so this suite runs serially.
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
  },
});
