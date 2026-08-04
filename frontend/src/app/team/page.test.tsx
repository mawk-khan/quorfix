import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test-utils";
import type { Membership, Session } from "@/lib/api/types";

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn(),
}));
vi.mock("@/lib/api/members", () => ({
  listMembers: vi.fn(),
  updateMemberRole: vi.fn(),
  removeMember: vi.fn(),
}));
vi.mock("@/lib/api/invitations", () => ({
  listInvitations: vi.fn().mockResolvedValue([]),
  createInvitation: vi.fn(),
  cancelInvitation: vi.fn(),
}));

import { getSession } from "@/lib/api/auth";
import { listMembers } from "@/lib/api/members";
import TeamPage from "./page";

const membersFixture: Membership[] = [
  {
    id: "m1",
    user: { id: "u1", email: "admin@example.com", first_name: "Ada", last_name: "Min" },
    role: "administrator",
    joined_at: new Date().toISOString(),
  },
  {
    id: "m2",
    user: { id: "u2", email: "dev@example.com", first_name: "Dev", last_name: "Eloper" },
    role: "developer",
    joined_at: new Date().toISOString(),
  },
];

function mockSession(role: Session["role"]): void {
  vi.mocked(getSession).mockResolvedValue({
    authenticated: true,
    role,
    user: { id: "me", email: "me@example.com", first_name: "Me", last_name: "" },
    organization: { id: "org1", name: "Acme", slug: "acme" },
  });
}

describe("TeamPage", () => {
  it("shows role controls and the invite form for an administrator", async () => {
    mockSession("administrator");
    vi.mocked(listMembers).mockResolvedValueOnce(membersFixture);
    renderWithProviders(<TeamPage />);

    expect(await screen.findByLabelText(/role for admin@example.com/i)).toBeInTheDocument();
    expect(screen.getByRole("form", { name: /invite a member/i })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /remove/i })).toHaveLength(2);
  });

  it("hides admin-only controls for a non-administrator", async () => {
    mockSession("developer");
    vi.mocked(listMembers).mockResolvedValueOnce(membersFixture);
    renderWithProviders(<TeamPage />);

    await screen.findByText("admin@example.com");
    expect(screen.queryByLabelText(/role for admin@example.com/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: /invite a member/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove/i })).not.toBeInTheDocument();
  });
});
