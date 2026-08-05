import { describe, expect, it } from "vitest";

import { formatDuration } from "./format";

describe("formatDuration", () => {
  it("renders null as a distinct 'no data' string, never zero", () => {
    expect(formatDuration(null)).toBe("No data");
  });

  it("renders sub-minute durations as <1m rather than 0m", () => {
    expect(formatDuration(30)).toBe("<1m");
  });

  it("renders minutes", () => {
    expect(formatDuration(45 * 60)).toBe("45m");
  });

  it("renders hours and minutes", () => {
    expect(formatDuration(2 * 3600 + 15 * 60)).toBe("2h 15m");
  });

  it("renders whole hours without a trailing 0m", () => {
    expect(formatDuration(3 * 3600)).toBe("3h");
  });

  it("renders days and hours", () => {
    expect(formatDuration(2 * 86400 + 4 * 3600)).toBe("2d 4h");
  });

  it("renders whole days without a trailing 0h", () => {
    expect(formatDuration(5 * 86400)).toBe("5d");
  });
});
