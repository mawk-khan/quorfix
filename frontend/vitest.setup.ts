import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// @testing-library/react's auto-cleanup detects Jest-style globals, which
// Vitest doesn't inject by default (no `test.globals: true` here) — without
// this, renders from earlier tests stay mounted and later queries can match
// multiple elements across tests.
afterEach(() => {
  cleanup();
});
