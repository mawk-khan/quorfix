import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test-utils";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn() }),
}));

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn().mockResolvedValue({
    authenticated: false,
    user: null,
    organization: null,
    role: null,
    demo_mode: false,
  }),
  login: vi.fn(),
  demoLogin: vi.fn(),
}));

import { demoLogin, getSession, login } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import SignInPage from "./page";

describe("SignInPage", () => {
  it("shows a validation error for an empty submission", async () => {
    renderWithProviders(<SignInPage />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(await screen.findByText(/enter a valid email address/i)).toBeInTheDocument();
  });

  it("submits valid credentials and redirects home", async () => {
    vi.mocked(login).mockResolvedValueOnce(undefined);
    renderWithProviders(<SignInPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email/i), "someone@example.com");
    await user.type(screen.getByLabelText(/password/i), "Str0ngPassw0rd!");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/"));
  });

  it("shows an error message when credentials are rejected", async () => {
    vi.mocked(login).mockRejectedValueOnce(
      new ApiError(400, { detail: "Invalid email or password." }),
    );
    renderWithProviders(<SignInPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email/i), "someone@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrong");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
  });

  describe("demo mode disabled (default)", () => {
    it("does not render the role selector", async () => {
      renderWithProviders(<SignInPage />);

      await screen.findByRole("button", { name: /^sign in$/i });
      expect(screen.queryByRole("group", { name: /explore quorfix by role/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^developer$/i })).not.toBeInTheDocument();
    });
  });

  describe("demo mode enabled", () => {
    function mockDemoMode() {
      vi.mocked(getSession).mockResolvedValue({
        authenticated: false,
        user: null,
        organization: null,
        role: null,
        demo_mode: true,
      });
    }

    it("renders the role selector with all five role buttons", async () => {
      mockDemoMode();
      renderWithProviders(<SignInPage />);

      const group = await screen.findByRole("group", { name: /explore quorfix by role/i });
      for (const label of ["Administrator", "Developer", "QA Tester", "Reporter", "Viewer"]) {
        expect(within(group).getByRole("button", { name: label })).toBeInTheDocument();
      }
    });

    it("submits the correct role identifier when a button is clicked", async () => {
      mockDemoMode();
      vi.mocked(demoLogin).mockResolvedValueOnce(undefined);
      renderWithProviders(<SignInPage />);
      const user = userEvent.setup();

      await user.click(await screen.findByRole("button", { name: "Developer" }));

      await waitFor(() => expect(demoLogin).toHaveBeenCalledWith("developer"));
      await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/"));
    });

    it("shows a per-role loading state and disables the other buttons", async () => {
      mockDemoMode();
      let resolveDemoLogin: () => void = () => {};
      vi.mocked(demoLogin).mockReturnValueOnce(
        new Promise((resolve) => {
          resolveDemoLogin = () => resolve(undefined);
        }),
      );
      renderWithProviders(<SignInPage />);
      const user = userEvent.setup();

      await user.click(await screen.findByRole("button", { name: "Developer" }));

      expect(await screen.findByText(/opening developer demo…/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Viewer" })).toBeDisabled();

      resolveDemoLogin();
      await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/"));
    });

    it("prevents duplicate submissions while a demo login is in progress", async () => {
      mockDemoMode();
      let resolveCount = 0;
      vi.mocked(demoLogin).mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveCount += 1;
            setTimeout(resolve, 20);
          }),
      );
      renderWithProviders(<SignInPage />);
      const user = userEvent.setup();

      const developerButton = await screen.findByRole("button", { name: "Developer" });
      await user.click(developerButton);
      // The button is now showing the loading label / disabled — this
      // second click must not fire a second request.
      await user.click(screen.getByRole("button", { name: /opening developer demo…/i }));

      await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/"));
      expect(resolveCount).toBe(1);
    });

    it("shows a generic error when the demo login request fails", async () => {
      mockDemoMode();
      vi.mocked(demoLogin).mockRejectedValueOnce(new ApiError(400, { detail: "nope" }));
      renderWithProviders(<SignInPage />);
      const user = userEvent.setup();

      await user.click(await screen.findByRole("button", { name: "Developer" }));

      expect(
        await screen.findByText(/couldn't open the demo right now/i),
      ).toBeInTheDocument();
    });

    it("still allows ordinary email/password sign-in", async () => {
      mockDemoMode();
      vi.mocked(login).mockResolvedValueOnce(undefined);
      renderWithProviders(<SignInPage />);
      const user = userEvent.setup();

      await screen.findByRole("group", { name: /explore quorfix by role/i });
      await user.type(screen.getByLabelText(/email/i), "someone@example.com");
      await user.type(screen.getByLabelText(/password/i), "Str0ngPassw0rd!");
      await user.click(screen.getByRole("button", { name: /^sign in$/i }));

      await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/"));
    });
  });
});
