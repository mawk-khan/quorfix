import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Project, Session } from "@/lib/api/types";
import { renderWithProviders } from "@/test-utils";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "p1" }),
}));

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn(),
}));
vi.mock("@/lib/api/members", () => ({
  listMembers: vi.fn().mockResolvedValue([]),
}));
vi.mock("@/lib/api/projects", () => ({
  getProject: vi.fn(),
  updateProject: vi.fn(),
  archiveProject: vi.fn(),
  restoreProject: vi.fn(),
}));

import { getSession } from "@/lib/api/auth";
import { archiveProject, getProject, restoreProject, updateProject } from "@/lib/api/projects";
import ProjectDetailPage from "./page";

function mockSession(role: Session["role"]): void {
  vi.mocked(getSession).mockResolvedValue({
    authenticated: true,
    role,
    user: { id: "me", email: "me@example.com", first_name: "Me", last_name: "" },
    organization: { id: "org1", name: "Acme", slug: "acme" },
  });
}

const activeProject: Project = {
  id: "p1",
  name: "Engine",
  key: "ENG",
  description: "The engine team",
  status: "active",
  lead: null,
  archived_at: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const archivedProject: Project = { ...activeProject, archived_at: new Date().toISOString() };

describe("ProjectDetailPage", () => {
  it("shows read-only fields and no mutation controls for a non-administrator", async () => {
    mockSession("developer");
    vi.mocked(getProject).mockResolvedValueOnce(activeProject);
    renderWithProviders(<ProjectDetailPage />);

    expect(await screen.findByText("The engine team")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: /edit project/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /archive project/i })).not.toBeInTheDocument();
  });

  it("shows an editable form and archive control for an administrator", async () => {
    mockSession("administrator");
    vi.mocked(getProject).mockResolvedValueOnce(activeProject);
    renderWithProviders(<ProjectDetailPage />);

    expect(await screen.findByRole("form", { name: /edit project/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^archive project$/i })).toBeInTheDocument();
  });

  it("submits an edit", async () => {
    mockSession("administrator");
    vi.mocked(getProject).mockResolvedValueOnce(activeProject);
    vi.mocked(updateProject).mockResolvedValueOnce({ ...activeProject, name: "Renamed" });
    renderWithProviders(<ProjectDetailPage />);
    const user = userEvent.setup();

    await screen.findByRole("form", { name: /edit project/i });
    const nameInput = screen.getByLabelText(/^name$/i);
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() =>
      expect(updateProject).toHaveBeenCalledWith("p1", expect.objectContaining({ name: "Renamed" })),
    );
  });

  it("requires confirmation before archiving", async () => {
    mockSession("administrator");
    vi.mocked(getProject).mockResolvedValueOnce(activeProject);
    vi.mocked(archiveProject).mockResolvedValueOnce(archivedProject);
    renderWithProviders(<ProjectDetailPage />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /^archive project$/i }));
    expect(screen.getByText(/archive this project\?/i)).toBeInTheDocument();
    expect(archiveProject).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /confirm/i }));
    await waitFor(() => expect(archiveProject).toHaveBeenCalledWith("p1"));
  });

  it("hides the edit form and offers restore for an archived project", async () => {
    mockSession("administrator");
    vi.mocked(getProject).mockResolvedValueOnce(archivedProject);
    renderWithProviders(<ProjectDetailPage />);

    expect(await screen.findByRole("button", { name: /restore project/i })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: /edit project/i })).not.toBeInTheDocument();
  });

  it("restores an archived project", async () => {
    mockSession("administrator");
    vi.mocked(getProject).mockResolvedValueOnce(archivedProject);
    vi.mocked(restoreProject).mockResolvedValueOnce(activeProject);
    renderWithProviders(<ProjectDetailPage />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /restore project/i }));
    await waitFor(() => expect(restoreProject).toHaveBeenCalledWith("p1"));
  });
});
