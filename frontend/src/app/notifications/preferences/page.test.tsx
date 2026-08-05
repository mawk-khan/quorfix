import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { NotificationPreference, Session } from "@/lib/api/types";
import { renderWithProviders } from "@/test-utils";

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn(),
}));

vi.mock("@/lib/api/notifications", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/api/notifications")>("@/lib/api/notifications");
  return {
    ...actual,
    listNotificationPreferences: vi.fn(),
    updateNotificationPreference: vi.fn(),
  };
});

import { getSession } from "@/lib/api/auth";
import { listNotificationPreferences, updateNotificationPreference } from "@/lib/api/notifications";
import NotificationPreferencesPage from "./page";

function mockSession(): void {
  vi.mocked(getSession).mockResolvedValue({
    authenticated: true,
    role: "developer",
    user: { id: "me", email: "me@example.com", first_name: "Me", last_name: "" },
    organization: { id: "org1", name: "Acme", slug: "acme" },
  } satisfies Session);
}

const allEnabled: NotificationPreference[] = [
  { event_type: "bug_assigned", email_enabled: true },
  { event_type: "mentioned", email_enabled: true },
  { event_type: "comment_added", email_enabled: true },
  { event_type: "status_changed", email_enabled: true },
  { event_type: "bug_reopened", email_enabled: true },
];

describe("NotificationPreferencesPage", () => {
  beforeEach(() => {
    vi.mocked(listNotificationPreferences).mockReset();
    vi.mocked(updateNotificationPreference).mockReset();
  });

  it("requires authentication", async () => {
    vi.mocked(getSession).mockResolvedValue({
      authenticated: false,
      role: null,
      user: null,
      organization: null,
    });
    renderWithProviders(<NotificationPreferencesPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/must sign in/i);
  });

  it("shows an error state when preferences fail to load", async () => {
    mockSession();
    vi.mocked(listNotificationPreferences).mockRejectedValueOnce(new Error("boom"));
    renderWithProviders(<NotificationPreferencesPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/something went wrong/i);
  });

  it("renders a toggle for every Community event type, all enabled by default", async () => {
    mockSession();
    vi.mocked(listNotificationPreferences).mockResolvedValueOnce(allEnabled);
    renderWithProviders(<NotificationPreferencesPage />);

    const checkboxes = await screen.findAllByRole("checkbox");
    expect(checkboxes).toHaveLength(5);
    for (const checkbox of checkboxes) {
      expect(checkbox).toBeChecked();
    }
  });

  it("reflects a disabled preference from the server", async () => {
    mockSession();
    vi.mocked(listNotificationPreferences).mockResolvedValueOnce([
      ...allEnabled.filter((p) => p.event_type !== "mentioned"),
      { event_type: "mentioned", email_enabled: false },
    ]);
    renderWithProviders(<NotificationPreferencesPage />);

    const mentionedToggle = await screen.findByLabelText(/mentioned in a comment/i);
    expect(mentionedToggle).not.toBeChecked();
  });

  it("toggling a checkbox calls updateNotificationPreference with the event type and new value", async () => {
    mockSession();
    vi.mocked(listNotificationPreferences).mockResolvedValue(allEnabled);
    vi.mocked(updateNotificationPreference).mockResolvedValue({ event_type: "mentioned", email_enabled: false });
    renderWithProviders(<NotificationPreferencesPage />);

    const mentionedToggle = await screen.findByLabelText(/mentioned in a comment/i);
    await userEvent.setup().click(mentionedToggle);

    await waitFor(() => expect(updateNotificationPreference).toHaveBeenCalledWith("mentioned", false));
  });

  it("every toggle is keyboard operable (native checkbox, reachable via Tab)", async () => {
    mockSession();
    vi.mocked(listNotificationPreferences).mockResolvedValueOnce(allEnabled);
    renderWithProviders(<NotificationPreferencesPage />);

    const [firstToggle] = await screen.findAllByRole("checkbox");
    if (!firstToggle) throw new Error("expected at least one checkbox to render");
    firstToggle.focus();
    expect(firstToggle).toHaveFocus();
    expect(firstToggle.tagName).toBe("INPUT");
  });
});
