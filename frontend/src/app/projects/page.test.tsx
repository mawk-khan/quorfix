import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PaginatedResponse, Project, Session } from "@/lib/api/types";
import { renderWithProviders } from "@/test-utils";

const replaceMock = vi.fn();
const routerMock = { replace: replaceMock };
let currentSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  usePathname: () => "/projects",
  useSearchParams: () => currentSearchParams,
}));

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn(),
}));
vi.mock("@/lib/api/projects", () => ({
  listProjects: vi.fn(),
}));

import { getSession } from "@/lib/api/auth";
import { listProjects } from "@/lib/api/projects";
import ProjectsPage from "./page";

function mockSession(role: Session["role"]): void {
  vi.mocked(getSession).mockResolvedValue({
    authenticated: true,
    role,
    user: { id: "me", email: "me@example.com", first_name: "Me", last_name: "" },
    organization: { id: "org1", name: "Acme", slug: "acme" },
  });
}

const projectFixture: Project = {
  id: "p1",
  name: "Engine",
  key: "ENG",
  description: "",
  status: "active",
  lead: null,
  archived_at: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

function paginated(results: Project[], count = results.length): PaginatedResponse<Project> {
  return { count, next: null, previous: null, results };
}

describe("ProjectsPage", () => {
  beforeEach(() => {
    currentSearchParams = new URLSearchParams();
    replaceMock.mockClear();
  });

  it("shows the New project link and the list for an administrator", async () => {
    mockSession("administrator");
    vi.mocked(listProjects).mockResolvedValueOnce(paginated([projectFixture]));
    renderWithProviders(<ProjectsPage />);

    expect(await screen.findByRole("link", { name: /new project/i })).toBeInTheDocument();
    expect(await screen.findByText("ENG")).toBeInTheDocument();
  });

  it("hides the New project link for a non-administrator", async () => {
    mockSession("developer");
    vi.mocked(listProjects).mockResolvedValueOnce(paginated([projectFixture]));
    renderWithProviders(<ProjectsPage />);

    await screen.findByText("ENG");
    expect(screen.queryByRole("link", { name: /new project/i })).not.toBeInTheDocument();
  });

  it("requires authentication", async () => {
    vi.mocked(getSession).mockResolvedValue({
      authenticated: false,
      role: null,
      user: null,
      organization: null,
    });
    renderWithProviders(<ProjectsPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/must sign in/i);
  });

  it("shows an empty state when there are no projects at all", async () => {
    mockSession("administrator");
    vi.mocked(listProjects).mockResolvedValueOnce(paginated([]));
    renderWithProviders(<ProjectsPage />);

    expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument();
  });

  it("shows a no-results state (distinct from empty) when a filter is active", async () => {
    currentSearchParams = new URLSearchParams("search=zzz");
    mockSession("administrator");
    vi.mocked(listProjects).mockResolvedValueOnce(paginated([]));
    renderWithProviders(<ProjectsPage />);

    expect(await screen.findByText(/no projects match your search/i)).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    mockSession("administrator");
    vi.mocked(listProjects).mockRejectedValueOnce(new Error("boom"));
    renderWithProviders(<ProjectsPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/something went wrong/i);
  });

  it("updates the URL when the search input changes", async () => {
    mockSession("administrator");
    vi.mocked(listProjects).mockResolvedValue(paginated([projectFixture]));
    renderWithProviders(<ProjectsPage />);
    const user = userEvent.setup();

    await screen.findByText("ENG");
    await user.type(screen.getByLabelText(/^search$/i), "e");

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/projects?search=e"));
  });

  it("updates the URL when the archived filter changes", async () => {
    mockSession("administrator");
    vi.mocked(listProjects).mockResolvedValue(paginated([projectFixture]));
    renderWithProviders(<ProjectsPage />);
    const user = userEvent.setup();

    await screen.findByText("ENG");
    await user.selectOptions(screen.getByLabelText(/^status$/i), "true");

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/projects?archived=true"));
  });
});
