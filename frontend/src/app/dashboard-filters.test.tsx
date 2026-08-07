import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ActiveProject } from "@/lib/api/types";
import type { DashboardFiltersValue } from "@/lib/dashboard/use-dashboard-filters";

import { DashboardFilters } from "./dashboard-filters";

const projects: ActiveProject[] = [
  { id: "p1", key: "BFW", name: "Quorfix Web", status: "active", total_bugs: 5, open_bugs: 2 },
];

const baseFilters: DashboardFiltersValue = {
  range: "30d",
  date_from: "2026-02-14",
  date_to: "2026-03-15",
  project: "",
};

describe("DashboardFilters", () => {
  it("marks the active preset with aria-pressed", () => {
    render(<DashboardFilters filters={baseFilters} projects={projects} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Last 30 days" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Last 7 days" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("selecting a preset calls onChange with that range", async () => {
    const onChange = vi.fn();
    render(<DashboardFilters filters={baseFilters} projects={projects} onChange={onChange} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Last 7 days" }));

    expect(onChange).toHaveBeenCalledWith({ range: "7d" });
  });

  it("changing the project select calls onChange with the project id", async () => {
    const onChange = vi.fn();
    render(<DashboardFilters filters={baseFilters} projects={projects} onChange={onChange} />);

    await userEvent.setup().selectOptions(screen.getByLabelText(/project/i), "p1");

    expect(onChange).toHaveBeenCalledWith({ project: "p1" });
  });

  it("switching to custom reveals date inputs seeded from the current range", async () => {
    const onChange = vi.fn();
    render(<DashboardFilters filters={baseFilters} projects={projects} onChange={onChange} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Custom" }));

    expect(onChange).toHaveBeenCalledWith({
      range: "custom",
      date_from: baseFilters.date_from,
      date_to: baseFilters.date_to,
    });
  });

  it("rejects a reversed custom range without calling onChange", async () => {
    const onChange = vi.fn();
    const customFilters: DashboardFiltersValue = { ...baseFilters, range: "custom" };
    render(<DashboardFilters filters={customFilters} projects={projects} onChange={onChange} />);

    const user = userEvent.setup();
    await user.clear(screen.getByLabelText(/from/i));
    await user.type(screen.getByLabelText(/from/i), "2026-03-20");
    await user.clear(screen.getByLabelText(/^to$/i));
    await user.type(screen.getByLabelText(/^to$/i), "2026-03-01");
    onChange.mockClear();
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(onChange).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent(/must not be before/i);
  });

  it("rejects a custom range longer than 366 days without calling onChange", async () => {
    const onChange = vi.fn();
    const customFilters: DashboardFiltersValue = { ...baseFilters, range: "custom" };
    render(<DashboardFilters filters={customFilters} projects={projects} onChange={onChange} />);

    const user = userEvent.setup();
    await user.clear(screen.getByLabelText(/from/i));
    await user.type(screen.getByLabelText(/from/i), "2020-01-01");
    await user.clear(screen.getByLabelText(/^to$/i));
    await user.type(screen.getByLabelText(/^to$/i), "2026-03-15");
    onChange.mockClear();
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(onChange).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent(/limited to 366 days/i);
  });

  it("accepts a valid custom range and calls onChange", async () => {
    const onChange = vi.fn();
    const customFilters: DashboardFiltersValue = { ...baseFilters, range: "custom" };
    render(<DashboardFilters filters={customFilters} projects={projects} onChange={onChange} />);

    const user = userEvent.setup();
    await user.clear(screen.getByLabelText(/from/i));
    await user.type(screen.getByLabelText(/from/i), "2026-03-01");
    await user.clear(screen.getByLabelText(/^to$/i));
    await user.type(screen.getByLabelText(/^to$/i), "2026-03-10");
    onChange.mockClear();
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(onChange).toHaveBeenCalledWith({
      range: "custom",
      date_from: "2026-03-01",
      date_to: "2026-03-10",
    });
  });
});
