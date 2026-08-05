import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { BugSummary, PaginatedResponse, ProjectRef, Session } from "@/lib/api/types";
import { renderWithProviders } from "@/test-utils";

const replaceMock = vi.fn();
const routerMock = { replace: replaceMock };
let currentSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  usePathname: () => "/bugs",
  useSearchParams: () => currentSearchParams,
}));

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn(),
}));
vi.mock("@/lib/api/bugs", () => ({
  listBugs: vi.fn(),
}));
vi.mock("@/lib/api/projects", () => ({
  listProjects: vi.fn().mockResolvedValue({ count: 0, next: null, previous: null, results: [] }),
}));

import { getSession } from "@/lib/api/auth";
import { listBugs } from "@/lib/api/bugs";
import BugsPage from "./page";

function mockSession(role: Session["role"]): void {
  vi.mocked(getSession).mockResolvedValue({
    authenticated: true,
    role,
    user: { id: "me", email: "me@example.com", first_name: "Me", last_name: "" },
    organization: { id: "org1", name: "Acme", slug: "acme" },
  });
}

const projectRef: ProjectRef = {
  id: "proj1",
  key: "ENG",
  name: "Engine",
};

const bugFixture: BugSummary = {
  id: "b1",
  key: "ENG-1",
  number: 1,
  project: projectRef,
  title: "Login button unresponsive",
  status: "new",
  priority: "high",
  severity: "major",
  reporter: { id: "u1", email: "reporter@example.com", first_name: "Rep", last_name: "" },
  assignee: null,
  due_date: null,
  archived_at: null,
  version: 1,
  is_watching: false,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

function paginated(results: BugSummary[], count = results.length): PaginatedResponse<BugSummary> {
  return { count, next: null, previous: null, results };
}

describe("BugsPage", () => {
  beforeEach(() => {
    currentSearchParams = new URLSearchParams();
    replaceMock.mockClear();
  });

  it("shows the New bug link and the list for a reporter", async () => {
    mockSession("reporter");
    vi.mocked(listBugs).mockResolvedValueOnce(paginated([bugFixture]));
    renderWithProviders(<BugsPage />);

    expect(await screen.findByRole("link", { name: /new bug/i })).toBeInTheDocument();
    expect(await screen.findByText("ENG-1")).toBeInTheDocument();
  });

  it("hides the New bug link for a viewer", async () => {
    mockSession("viewer");
    vi.mocked(listBugs).mockResolvedValueOnce(paginated([bugFixture]));
    renderWithProviders(<BugsPage />);

    await screen.findByText("ENG-1");
    expect(screen.queryByRole("link", { name: /new bug/i })).not.toBeInTheDocument();
  });

  it("requires authentication", async () => {
    vi.mocked(getSession).mockResolvedValue({
      authenticated: false,
      role: null,
      user: null,
      organization: null,
    });
    renderWithProviders(<BugsPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/must sign in/i);
  });

  it("shows an empty state when there are no bugs at all", async () => {
    mockSession("administrator");
    vi.mocked(listBugs).mockResolvedValueOnce(paginated([]));
    renderWithProviders(<BugsPage />);

    expect(await screen.findByText(/no bugs yet/i)).toBeInTheDocument();
  });

  it("shows a no-results state (distinct from empty) when a filter is active", async () => {
    currentSearchParams = new URLSearchParams("search=zzz");
    mockSession("administrator");
    vi.mocked(listBugs).mockResolvedValueOnce(paginated([]));
    renderWithProviders(<BugsPage />);

    expect(await screen.findByText(/no bugs match your search/i)).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    mockSession("administrator");
    vi.mocked(listBugs).mockRejectedValueOnce(new Error("boom"));
    renderWithProviders(<BugsPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/something went wrong/i);
  });

  it("updates the URL when the search input changes", async () => {
    mockSession("administrator");
    vi.mocked(listBugs).mockResolvedValue(paginated([bugFixture]));
    renderWithProviders(<BugsPage />);

    await screen.findByText("ENG-1");
    await userEvent.setup().type(screen.getByLabelText(/^search$/i), "e");

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/bugs?search=e"));
  });
});
