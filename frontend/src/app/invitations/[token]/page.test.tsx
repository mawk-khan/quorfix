import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test-utils";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  useParams: () => ({ token: "test-token" }),
}));

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn().mockResolvedValue({
    authenticated: false,
    user: null,
    organization: null,
    role: null,
  }),
}));

vi.mock("@/lib/api/invitations", () => ({
  getInvitation: vi.fn(),
  acceptInvitation: vi.fn(),
}));

import { acceptInvitation, getInvitation } from "@/lib/api/invitations";
import InvitationAcceptPage from "./page";

describe("InvitationAcceptPage", () => {
  it("shows an invalid message when the invitation is expired or revoked", async () => {
    vi.mocked(getInvitation).mockRejectedValueOnce(new Error("not found"));
    renderWithProviders(<InvitationAcceptPage />);

    expect(await screen.findByText(/invalid or has expired/i)).toBeInTheDocument();
  });

  it("shows the accept form for a valid invitation", async () => {
    vi.mocked(getInvitation).mockResolvedValueOnce({
      organization_name: "Acme",
      email: "new@example.com",
      role: "developer",
      expires_at: new Date().toISOString(),
    });
    renderWithProviders(<InvitationAcceptPage />);

    expect(await screen.findByRole("heading", { name: /join acme/i })).toBeInTheDocument();
  });

  it("accepts the invitation and redirects home", async () => {
    vi.mocked(getInvitation).mockResolvedValueOnce({
      organization_name: "Acme",
      email: "new@example.com",
      role: "developer",
      expires_at: new Date().toISOString(),
    });
    vi.mocked(acceptInvitation).mockResolvedValueOnce(undefined);
    renderWithProviders(<InvitationAcceptPage />);
    const user = userEvent.setup();

    await screen.findByRole("heading", { name: /join acme/i });
    await user.type(screen.getByLabelText(/password/i), "Str0ngPassw0rd!");
    await user.click(screen.getByRole("button", { name: /accept invitation/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/"));
  });
});
