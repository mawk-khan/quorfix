import { describe, expect, it } from "vitest";

import {
  computePresetRange,
  isExcessiveRange,
  isReversedRange,
  isValidISODate,
  toISODate,
} from "./date-range";

describe("computePresetRange", () => {
  it("7-day preset spans exactly 7 calendar days: today plus the previous 6", () => {
    const today = new Date(2026, 2, 15); // March 15, 2026 (local)
    const { date_from, date_to } = computePresetRange("7d", today);

    expect(date_to).toBe("2026-03-15");
    expect(date_from).toBe("2026-03-09"); // 6 days before the 15th
  });

  it("7-day preset never produces an accidental 8-day inclusive range", () => {
    const today = new Date(2026, 2, 15);
    const { date_from, date_to } = computePresetRange("7d", today);
    const days =
      (new Date(`${date_to}T00:00:00`).getTime() - new Date(`${date_from}T00:00:00`).getTime()) /
        86_400_000 +
      1;
    expect(days).toBe(7);
  });

  it("30-day preset spans exactly 30 calendar days", () => {
    const today = new Date(2026, 0, 31);
    const { date_from, date_to } = computePresetRange("30d", today);
    const days =
      (new Date(`${date_to}T00:00:00`).getTime() - new Date(`${date_from}T00:00:00`).getTime()) /
        86_400_000 +
      1;
    expect(days).toBe(30);
  });

  it("90-day preset spans exactly 90 calendar days", () => {
    const today = new Date(2026, 5, 1);
    const { date_from, date_to } = computePresetRange("90d", today);
    const days =
      (new Date(`${date_to}T00:00:00`).getTime() - new Date(`${date_from}T00:00:00`).getTime()) /
        86_400_000 +
      1;
    expect(days).toBe(90);
  });

  it("crosses a month/year boundary correctly", () => {
    const today = new Date(2026, 0, 3); // Jan 3, 2026
    const { date_from } = computePresetRange("7d", today);
    expect(date_from).toBe("2025-12-28");
  });
});

describe("toISODate", () => {
  it("uses the local calendar date, not UTC", () => {
    const date = new Date(2026, 6, 4); // July 4, 2026, local midnight
    expect(toISODate(date)).toBe("2026-07-04");
  });
});

describe("isValidISODate", () => {
  it("accepts a well-formed date", () => {
    expect(isValidISODate("2026-03-15")).toBe(true);
  });

  it("rejects malformed input", () => {
    expect(isValidISODate("not-a-date")).toBe(false);
    expect(isValidISODate("2026-13-01")).toBe(false);
    expect(isValidISODate("2026-02-30")).toBe(false);
  });
});

describe("isReversedRange", () => {
  it("flags date_to before date_from", () => {
    expect(isReversedRange("2026-03-10", "2026-03-01")).toBe(true);
  });

  it("allows date_to on or after date_from", () => {
    expect(isReversedRange("2026-03-01", "2026-03-01")).toBe(false);
    expect(isReversedRange("2026-03-01", "2026-03-02")).toBe(false);
  });
});

describe("isExcessiveRange", () => {
  it("allows a 366-day inclusive span", () => {
    expect(isExcessiveRange("2026-01-01", "2027-01-01")).toBe(false);
  });

  it("rejects a span longer than 366 days", () => {
    expect(isExcessiveRange("2026-01-01", "2027-01-02")).toBe(true);
  });
});
