import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ActiveProject,
  AnalyticsSummary,
  Distributions,
  PaginatedResponse,
  ResolutionTimeEntry,
  DashboardActivity,
  Session,
  TrendPoint,
  Workload,
} from "@/lib/api/types";
import { SessionProvider } from "@/lib/auth/session-provider";
import { renderWithProviders } from "@/test-utils";

// Local variant of renderWithProviders that also exposes a same-providers
// rerender — needed only by the project-filter-change test below, which
// must re-render through the identical QueryClientProvider/SessionProvider
// (a bare `rerender(<HomePage />)` would unmount them and break every
// hook that depends on that context).
function renderApp(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrap = (element: ReactElement) => (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>{element}</SessionProvider>
    </QueryClientProvider>
  );
  const result = render(wrap(ui));
  return { ...result, rerenderApp: (nextUi: ReactElement) => result.rerender(wrap(nextUi)) };
}

const replaceMock = vi.fn();
const routerMock = { replace: replaceMock, push: vi.fn() };
let currentSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  usePathname: () => "/",
  useSearchParams: () => currentSearchParams,
}));

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("@/lib/api/analytics", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/analytics")>("@/lib/api/analytics");
  return {
    ...actual,
    getSummary: vi.fn(),
    getTrends: vi.fn(),
    getResolutionTime: vi.fn(),
    getDistributions: vi.fn(),
    getWorkload: vi.fn(),
    getRecentActivity: vi.fn(),
    getActiveProjects: vi.fn(),
  };
});

import { getSession } from "@/lib/api/auth";
import {
  getActiveProjects,
  getDistributions,
  getRecentActivity,
  getResolutionTime,
  getSummary,
  getTrends,
  getWorkload,
} from "@/lib/api/analytics";
import HomePage from "./page";

function mockSession(): void {
  vi.mocked(getSession).mockResolvedValue({
    authenticated: true,
    role: "administrator",
    user: { id: "me", email: "me@example.com", first_name: "Ada", last_name: "Lovelace" },
    organization: { id: "org1", name: "Acme", slug: "acme" },
  } satisfies Session);
}

const summaryFixture: AnalyticsSummary = {
  open_bugs: 5,
  overdue_bugs: 1,
  new_bugs: 6,
  resolved_bugs: 2,
};

const trendsFixture: TrendPoint[] = [
  { date: "2026-03-14", created: 2, resolved: 0 },
  { date: "2026-03-15", created: 1, resolved: 1 },
];

const resolutionTimeFixture: ResolutionTimeEntry[] = [
  { priority: "urgent", average_seconds: 3600 },
  { priority: "high", average_seconds: null },
  { priority: "medium", average_seconds: 7200 },
  { priority: "low", average_seconds: null },
];

const distributionsFixture: Distributions = {
  status: [
    { status: "new", count: 2 },
    { status: "triaged", count: 1 },
  ],
  severity: [
    { severity: "blocker", count: 1 },
    { severity: "trivial", count: 0 },
  ],
};

const workloadFixture: Workload = {
  eligible: [{ user_id: "u1", name: "Dev User", role: "developer", count: 3 }],
  unassigned: 2,
  needs_reassignment: [],
};

const activeProjectsFixture: ActiveProject[] = [
  { id: "p1", key: "BFW", name: "Bug Fixer Web", status: "active", total_bugs: 5, open_bugs: 3 },
];

function recentActivityPage(): PaginatedResponse<DashboardActivity> {
  return { count: 0, next: null, previous: null, results: [] };
}

function mockAllQueriesToResolve(): void {
  vi.mocked(getSummary).mockResolvedValue(summaryFixture);
  vi.mocked(getTrends).mockResolvedValue(trendsFixture);
  vi.mocked(getResolutionTime).mockResolvedValue(resolutionTimeFixture);
  vi.mocked(getDistributions).mockResolvedValue(distributionsFixture);
  vi.mocked(getWorkload).mockResolvedValue(workloadFixture);
  vi.mocked(getActiveProjects).mockResolvedValue(activeProjectsFixture);
  vi.mocked(getRecentActivity).mockResolvedValue(recentActivityPage());
}

describe("Dashboard (HomePage)", () => {
  beforeEach(() => {
    currentSearchParams = new URLSearchParams();
    replaceMock.mockClear();
    vi.mocked(getSummary).mockReset();
    vi.mocked(getTrends).mockReset();
    vi.mocked(getResolutionTime).mockReset();
    vi.mocked(getDistributions).mockReset();
    vi.mocked(getWorkload).mockReset();
    vi.mocked(getRecentActivity).mockReset();
    vi.mocked(getActiveProjects).mockReset();
  });

  it("shows the signed-out landing view, not dashboard data", async () => {
    vi.mocked(getSession).mockResolvedValue({
      authenticated: false,
      role: null,
      user: null,
      organization: null,
    });
    renderWithProviders(<HomePage />);

    expect(await screen.findByRole("heading", { name: "Bug Fixer" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  });

  it("renders every section's data on a successful load", async () => {
    mockSession();
    mockAllQueriesToResolve();
    renderWithProviders(<HomePage />);

    expect(await screen.findByText("5")).toBeInTheDocument(); // open bugs
    expect(screen.getByText("Dev User")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "BFW" })).toBeInTheDocument();
  });

  it("one section failing does not hide the others (partial dashboard remains visible)", async () => {
    mockSession();
    mockAllQueriesToResolve();
    vi.mocked(getSummary).mockReset();
    vi.mocked(getSummary).mockRejectedValue(new Error("summary boom"));
    renderWithProviders(<HomePage />);

    // The failing section shows its own error + retry…
    await waitFor(() => {
      expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByRole("button", { name: /retry/i }).length).toBeGreaterThan(0);

    // …while unrelated sections still render their real data.
    expect(await screen.findByText("Dev User")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "BFW" })).toBeInTheDocument();
  });

  it("restores filters from the URL and requests that exact range/project", async () => {
    currentSearchParams = new URLSearchParams("range=7d&project=p1");
    mockSession();
    mockAllQueriesToResolve();
    renderWithProviders(<HomePage />);

    await waitFor(() => expect(getSummary).toHaveBeenCalled());
    const call = vi.mocked(getSummary).mock.calls[0]?.[0];
    expect(call?.project).toBe("p1");
    // 7-day preset: exactly a 7-day inclusive span.
    const days =
      (new Date(`${call!.date_to}T00:00:00`).getTime() -
        new Date(`${call!.date_from}T00:00:00`).getTime()) /
        86_400_000 +
      1;
    expect(days).toBe(7);
  });

  it("point-in-time sections (distributions/workload) refetch when the project filter changes", async () => {
    mockSession();
    mockAllQueriesToResolve();
    const { rerenderApp } = renderApp(<HomePage />);

    await screen.findByText("Dev User");
    vi.mocked(getDistributions).mockClear();
    vi.mocked(getWorkload).mockClear();

    await userEvent.setup().selectOptions(screen.getByLabelText(/project/i), "p1");

    // The mocked router records the intended URL but (unlike real Next.js
    // navigation) doesn't itself re-invoke useSearchParams() — apply the
    // resulting URL to the mock and re-render, the same effect a real App
    // Router navigation would have.
    await waitFor(() => expect(replaceMock).toHaveBeenCalled());
    const [url] = replaceMock.mock.calls.at(-1)!;
    currentSearchParams = new URLSearchParams(String(url).split("?")[1] ?? "");
    rerenderApp(<HomePage />);

    await waitFor(() => {
      expect(getDistributions).toHaveBeenCalledWith({ project: "p1" });
      expect(getWorkload).toHaveBeenCalledWith({ project: "p1" });
    });
  });

  it("distributions and workload sections are visibly labeled as NOT date-scoped", async () => {
    mockSession();
    mockAllQueriesToResolve();
    renderWithProviders(<HomePage />);

    await screen.findByText("Dev User");
    const statusSection = screen.getByRole("heading", { name: "Bugs by status" }).closest("section")!;
    expect(within(statusSection).getByText(/not affected by the date range/i)).toBeInTheDocument();

    const workloadSection = screen
      .getByRole("heading", { name: "Bugs per developer" })
      .closest("section")!;
    expect(within(workloadSection).getByText(/not affected by the date range/i)).toBeInTheDocument();
  });

  it("the bug trends chart exposes a text alternative with the same values shown visually", async () => {
    mockSession();
    mockAllQueriesToResolve();
    renderWithProviders(<HomePage />);

    const table = await screen.findByRole("table", {
      name: /bugs created and resolved per day/i,
    });
    // The visually-hidden table carries the exact same figures the chart plots.
    expect(within(table).getByText("2")).toBeInTheDocument();
    expect(within(table).getAllByText("1").length).toBeGreaterThan(0);
  });
});
