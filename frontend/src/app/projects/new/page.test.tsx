import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Session } from "@/lib/api/types";
import { renderWithProviders } from "@/test-utils";

const pushMock = vi.fn();
const routerMock = { push: pushMock };

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
}));

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn(),
}));
vi.mock("@/lib/api/members", () => ({
  listMembers: vi.fn().mockResolvedValue([]),
}));
vi.mock("@/lib/api/projects", () => ({
  createProject: vi.fn(),
}));

import { getSession } from "@/lib/api/auth";
import { createProject } from "@/lib/api/projects";
import NewProjectPage from "./page";

function mockSession(role: Session["role"]): void {
  vi.mocked(getSession).mockResolvedValue({
    authenticated: true,
    role,
    user: { id: "me", email: "me@example.com", first_name: "Me", last_name: "" },
    organization: { id: "org1", name: "Acme", slug: "acme" },
  });
}

describe("NewProjectPage", () => {
  it("shows a permission error for a non-administrator", async () => {
    mockSession("developer");
    renderWithProviders(<NewProjectPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/do not have permission/i);
  });

  it("shows validation errors for an empty submission", async () => {
    mockSession("administrator");
    renderWithProviders(<NewProjectPage />);
    const user = userEvent.setup();

    const submitButton = await screen.findByRole("button", { name: /create project/i });
    await user.click(submitButton);

    expect(await screen.findByText(/name is required/i)).toBeInTheDocument();
  });

  it("rejects an invalid key format", async () => {
    mockSession("administrator");
    renderWithProviders(<NewProjectPage />);
    const user = userEvent.setup();

    await screen.findByRole("button", { name: /create project/i });
    await user.type(screen.getByLabelText(/^name$/i), "Engine");
    await user.type(screen.getByLabelText(/^key$/i), "1");
    await user.click(screen.getByRole("button", { name: /create project/i }));

    expect(await screen.findByText(/must be 2-10 characters/i)).toBeInTheDocument();
    expect(createProject).not.toHaveBeenCalled();
  });

  it("normalizes the key to uppercase and navigates to the new project on success", async () => {
    mockSession("administrator");
    vi.mocked(createProject).mockResolvedValueOnce({
      id: "p1",
      name: "Engine",
      key: "ENG",
      description: "",
      status: "active",
      lead: null,
      archived_at: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    renderWithProviders(<NewProjectPage />);
    const user = userEvent.setup();

    await screen.findByRole("button", { name: /create project/i });
    await user.type(screen.getByLabelText(/^name$/i), "Engine");
    await user.type(screen.getByLabelText(/^key$/i), "eng");
    await user.click(screen.getByRole("button", { name: /create project/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/projects/p1"));
    expect(createProject).toHaveBeenCalledWith(expect.objectContaining({ name: "Engine", key: "ENG" }));
  });
});
