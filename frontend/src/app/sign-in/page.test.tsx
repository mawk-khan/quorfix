import { screen, waitFor } from "@testing-library/react";
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
  }),
  login: vi.fn(),
}));

import { login } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import SignInPage from "./page";

describe("SignInPage", () => {
  it("shows a validation error for an empty submission", async () => {
    renderWithProviders(<SignInPage />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/enter a valid email address/i)).toBeInTheDocument();
  });

  it("submits valid credentials and redirects home", async () => {
    vi.mocked(login).mockResolvedValueOnce(undefined);
    renderWithProviders(<SignInPage />);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email/i), "someone@example.com");
    await user.type(screen.getByLabelText(/password/i), "Str0ngPassw0rd!");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

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
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
  });
});
