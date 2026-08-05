import { render, screen } from "@testing-library/react";
import type { UseQueryResult } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import type { Workload } from "@/lib/api/types";

import { DeveloperWorkload } from "./developer-workload";

function queryWith(data: Workload | undefined, overrides: Partial<UseQueryResult<Workload>> = {}) {
  return {
    data,
    isLoading: false,
    isError: false,
    error: null,
    refetch: () => {},
    ...overrides,
  } as unknown as UseQueryResult<Workload>;
}

describe("DeveloperWorkload", () => {
  it("shows a loading skeleton while pending", () => {
    render(<DeveloperWorkload query={queryWith(undefined, { isLoading: true })} />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows an error and a retry control on failure", () => {
    render(
      <DeveloperWorkload
        query={queryWith(undefined, { isError: true, error: new Error("boom") })}
      />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("shows an empty state when there is no open workload at all", () => {
    render(
      <DeveloperWorkload
        query={queryWith({ eligible: [], unassigned: 0, needs_reassignment: [] })}
      />,
    );
    expect(screen.getByText(/no open bugs to assign/i)).toBeInTheDocument();
  });

  it("renders eligible assignees and the unassigned row", () => {
    render(
      <DeveloperWorkload
        query={queryWith({
          eligible: [{ user_id: "u1", name: "Dev User", role: "developer", count: 3 }],
          unassigned: 2,
          needs_reassignment: [],
        })}
      />,
    );
    expect(screen.getByText("Dev User")).toBeInTheDocument();
    expect(screen.getByText("Unassigned")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("needs-reassignment rows are visibly distinct from the unassigned row", () => {
    render(
      <DeveloperWorkload
        query={queryWith({
          eligible: [],
          unassigned: 1,
          needs_reassignment: [{ user_id: "u2", name: "Former Dev", role: "reporter", count: 1 }],
        })}
      />,
    );

    // "Former Dev" carries an explicit "Needs reassignment" badge — never
    // silently folded into the same row/label as "Unassigned".
    const formerDevRow = screen.getByText("Former Dev").closest("tr");
    expect(formerDevRow).toHaveTextContent("Needs reassignment");

    const unassignedRow = screen.getByText("Unassigned").closest("tr");
    expect(unassignedRow).not.toHaveTextContent("Needs reassignment");

    // A visible explanatory note distinguishes the two, not color alone.
    expect(screen.getByText(/distinct from .*unassigned/i)).toBeInTheDocument();
  });

  it("is an accessible table with a caption and column headers", () => {
    render(
      <DeveloperWorkload
        query={queryWith({
          eligible: [{ user_id: "u1", name: "Dev User", role: "developer", count: 1 }],
          unassigned: 0,
          needs_reassignment: [],
        })}
      />,
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /assignee/i })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /open bugs/i })).toBeInTheDocument();
  });
});
