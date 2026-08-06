import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PaginatedResponse, Project, Session } from "@/lib/api/types";
import { renderWithProviders } from "@/test-utils";

const pushMock = vi.fn();
const routerMock = { push: pushMock };

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
}));

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn(),
}));
vi.mock("@/lib/api/bugs", () => ({
  createBug: vi.fn(),
}));
vi.mock("@/lib/api/projects", () => ({
  listProjects: vi.fn(),
}));

import { getSession } from "@/lib/api/auth";
import { createBug } from "@/lib/api/bugs";
import { listProjects } from "@/lib/api/projects";
import NewBugPage from "./page";

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

function paginated(results: Project[]): PaginatedResponse<Project> {
  return { count: results.length, next: null, previous: null, results };
}

describe("NewBugPage", () => {
  it("shows a permission error for a viewer", async () => {
    mockSession("viewer");
    vi.mocked(listProjects).mockResolvedValueOnce(paginated([projectFixture]));
    renderWithProviders(<NewBugPage />);

    expect(await screen.findByRole("heading", { name: /access restricted/i })).toBeInTheDocument();
    expect(screen.getByText(/do not have permission to create bugs/i)).toBeInTheDocument();
  });

  it("allows a reporter to reach the form", async () => {
    mockSession("reporter");
    vi.mocked(listProjects).mockResolvedValueOnce(paginated([projectFixture]));
    renderWithProviders(<NewBugPage />);

    expect(await screen.findByRole("form", { name: /create bug/i })).toBeInTheDocument();
  });

  it("shows validation errors for an empty submission", async () => {
    mockSession("administrator");
    vi.mocked(listProjects).mockResolvedValueOnce(paginated([projectFixture]));
    renderWithProviders(<NewBugPage />);
    const user = userEvent.setup();

    const submitButton = await screen.findByRole("button", { name: /create bug/i });
    await user.click(submitButton);

    expect(await screen.findByText(/project is required/i)).toBeInTheDocument();
    expect(createBug).not.toHaveBeenCalled();
  });

  it("submits and navigates to the new bug on success", async () => {
    mockSession("administrator");
    vi.mocked(listProjects).mockResolvedValueOnce(paginated([projectFixture]));
    vi.mocked(createBug).mockResolvedValueOnce({
      id: "b1",
      key: "ENG-1",
      number: 1,
      project: { id: "p1", key: "ENG", name: "Engine" },
      title: "Something broke",
      description: "",
      steps_to_reproduce: "",
      expected_result: "",
      actual_result: "",
      environment: "",
      category: "",
      status: "new",
      priority: "medium",
      severity: "major",
      reporter: { id: "me", email: "me@example.com", first_name: "Me", last_name: "" },
      assignee: null,
      due_date: null,
      resolved_at: null,
      closed_at: null,
      archived_at: null,
      version: 1,
      tags: [],
      watcher_count: 0,
      is_watching: false,
      available_transitions: [],
      editable_fields: [],
      can_assign: false,
      can_archive: false,
      can_manage_relationships: false,
      relationships: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    renderWithProviders(<NewBugPage />);
    const user = userEvent.setup();

    await screen.findByRole("form", { name: /create bug/i });
    await screen.findByRole("option", { name: /ENG — Engine/ });
    await user.selectOptions(screen.getByLabelText(/^project$/i), "p1");
    await user.type(screen.getByLabelText(/^title$/i), "Something broke");
    await user.click(screen.getByRole("button", { name: /create bug/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/bugs/b1"));
    expect(createBug).toHaveBeenCalledWith(expect.objectContaining({ project: "p1", title: "Something broke" }));
  });
});
