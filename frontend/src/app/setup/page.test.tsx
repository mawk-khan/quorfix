import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test-utils";

const pushMock = vi.fn();
const replaceMock = vi.fn();
// Next's real useRouter() returns a stable reference across renders. A
// fresh object literal here would make useEffect's [router] dependency
// look "changed" on every render, re-firing the effect and consuming the
// mocked getSetupStatus()'s one-time resolved value more than once.
const routerMock = { push: pushMock, replace: replaceMock };

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
}));

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn().mockResolvedValue({
    authenticated: false,
    user: null,
    organization: null,
    role: null,
  }),
}));

vi.mock("@/lib/api/setup", () => ({
  getSetupStatus: vi.fn(),
  submitSetup: vi.fn(),
}));

import { getSetupStatus, submitSetup } from "@/lib/api/setup";
import SetupPage from "./page";

describe("SetupPage", () => {
  it("redirects to sign-in when the instance is already configured", async () => {
    vi.mocked(getSetupStatus).mockResolvedValueOnce({ is_configured: true });
    renderWithProviders(<SetupPage />);

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/sign-in"));
  });

  it("shows validation errors for an empty submission when not configured", async () => {
    vi.mocked(getSetupStatus).mockResolvedValueOnce({ is_configured: false });
    renderWithProviders(<SetupPage />);
    const user = userEvent.setup();

    const submitButton = await screen.findByRole("button", {
      name: /create administrator account/i,
    });
    await user.click(submitButton);

    expect(await screen.findByText(/organization name is required/i)).toBeInTheDocument();
  });

  it("submits valid data and redirects home", async () => {
    vi.mocked(getSetupStatus).mockResolvedValueOnce({ is_configured: false });
    vi.mocked(submitSetup).mockResolvedValueOnce(undefined);
    renderWithProviders(<SetupPage />);
    const user = userEvent.setup();

    await screen.findByRole("button", { name: /create administrator account/i });
    await user.type(screen.getByLabelText(/organization name/i), "Acme");
    await user.type(screen.getByLabelText(/your email/i), "admin@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "Str0ngPassw0rd!");
    await user.click(screen.getByRole("button", { name: /create administrator account/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/"));
  });
});
