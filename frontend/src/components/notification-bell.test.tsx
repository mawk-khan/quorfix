import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Notification, PaginatedResponse } from "@/lib/api/types";
import { renderWithProviders } from "@/test-utils";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/lib/api/notifications", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/api/notifications")>("@/lib/api/notifications");
  return {
    ...actual,
    getUnreadCount: vi.fn(),
    listNotifications: vi.fn(),
    markNotificationRead: vi.fn(),
    markAllNotificationsRead: vi.fn(),
  };
});

import {
  getUnreadCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/api/notifications";
import { NotificationBell } from "./notification-bell";

function paginated(results: Notification[]): PaginatedResponse<Notification> {
  return { count: results.length, next: null, previous: null, results };
}

const notificationFixture: Notification = {
  id: "n1",
  event_type: "bug_assigned",
  actor: { id: "u1", email: "actor@example.com", first_name: "Ada", last_name: "Lovelace" },
  bug: { id: "b1", key: "ENG-1", title: "Login broken", status: "new" },
  comment_id: null,
  read_at: null,
  email_status: "pending",
  created_at: new Date().toISOString(),
  target_url: "/bugs/b1",
};

describe("NotificationBell", () => {
  beforeEach(() => {
    pushMock.mockClear();
    vi.mocked(getUnreadCount).mockReset();
    vi.mocked(listNotifications).mockReset();
    vi.mocked(markNotificationRead).mockReset();
    vi.mocked(markAllNotificationsRead).mockReset();
  });

  it("shows the unread count as an accessible label and a visible badge", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ count: 3 });
    renderWithProviders(<NotificationBell />);

    const trigger = await screen.findByRole("button", { name: /notifications, 3 unread/i });
    expect(within(trigger).getByText("3")).toBeInTheDocument();
  });

  it("does not fetch the dropdown list until it is opened", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ count: 0 });
    vi.mocked(listNotifications).mockResolvedValue(paginated([]));
    renderWithProviders(<NotificationBell />);

    await screen.findByRole("button", { name: /^notifications$/i });
    expect(listNotifications).not.toHaveBeenCalled();

    await userEvent.setup().click(screen.getByRole("button", { name: /^notifications$/i }));
    await waitFor(() => expect(listNotifications).toHaveBeenCalled());
  });

  it("shows a loading state while the dropdown list is fetching", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ count: 0 });
    vi.mocked(listNotifications).mockReturnValue(new Promise(() => {})); // never resolves
    renderWithProviders(<NotificationBell />);

    await userEvent.setup().click(await screen.findByRole("button", { name: /^notifications$/i }));
    expect(await screen.findByText(/loading/i)).toBeInTheDocument();
  });

  it("shows an error state when the dropdown list fails to load", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ count: 0 });
    vi.mocked(listNotifications).mockRejectedValue(new Error("boom"));
    renderWithProviders(<NotificationBell />);

    await userEvent.setup().click(await screen.findByRole("button", { name: /^notifications$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load/i);
  });

  it("shows an empty state when there are no notifications", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ count: 0 });
    vi.mocked(listNotifications).mockResolvedValue(paginated([]));
    renderWithProviders(<NotificationBell />);

    await userEvent.setup().click(await screen.findByRole("button", { name: /^notifications$/i }));
    expect(await screen.findByText(/no notifications yet/i)).toBeInTheDocument();
  });

  it("marks a notification read and navigates when clicked", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ count: 1 });
    vi.mocked(listNotifications).mockResolvedValue(paginated([notificationFixture]));
    vi.mocked(markNotificationRead).mockResolvedValue({ ...notificationFixture, read_at: new Date().toISOString() });
    renderWithProviders(<NotificationBell />);

    await userEvent.setup().click(await screen.findByRole("button", { name: /notifications, 1 unread/i }));
    const item = await screen.findByText(/ada lovelace assigned you/i);
    await userEvent.setup().click(item);

    // React Query's mutation runner invokes mutationFn with an internal
    // context object as a second argument — only the first (our own "n1")
    // is ever meaningful to markNotificationRead's own signature.
    await waitFor(() => expect(vi.mocked(markNotificationRead).mock.calls[0]?.[0]).toBe("n1"));
    expect(pushMock).toHaveBeenCalledWith("/bugs/b1");
  });

  it("navigates even if marking read fails — navigation is never blocked by the mutation", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ count: 1 });
    vi.mocked(listNotifications).mockResolvedValue(paginated([notificationFixture]));
    vi.mocked(markNotificationRead).mockRejectedValue(new Error("network down"));
    renderWithProviders(<NotificationBell />);

    await userEvent.setup().click(await screen.findByRole("button", { name: /notifications, 1 unread/i }));
    const item = await screen.findByText(/ada lovelace assigned you/i);
    await userEvent.setup().click(item);

    expect(pushMock).toHaveBeenCalledWith("/bugs/b1");
  });

  it("mark all read is disabled at zero unread and enabled otherwise", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ count: 1 });
    vi.mocked(listNotifications).mockResolvedValue(paginated([notificationFixture]));
    vi.mocked(markAllNotificationsRead).mockResolvedValue({ updated: 1 });
    renderWithProviders(<NotificationBell />);

    await userEvent.setup().click(await screen.findByRole("button", { name: /notifications, 1 unread/i }));
    const markAllButton = await screen.findByRole("button", { name: /mark all read/i });
    expect(markAllButton).toBeEnabled();

    await userEvent.setup().click(markAllButton);
    await waitFor(() => expect(markAllNotificationsRead).toHaveBeenCalled());
  });

  it("links the trigger to the open panel via aria-controls", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ count: 0 });
    vi.mocked(listNotifications).mockResolvedValue(paginated([]));
    renderWithProviders(<NotificationBell />);

    const trigger = await screen.findByRole("button", { name: /^notifications$/i });
    expect(trigger).not.toHaveAttribute("aria-controls");

    await userEvent.setup().click(trigger);
    const panel = await screen.findByLabelText(/recent notifications/i);
    expect(panel).toHaveAttribute("id", trigger.getAttribute("aria-controls"));
  });

  it("closes on Escape and returns focus to the trigger button", async () => {
    vi.mocked(getUnreadCount).mockResolvedValue({ count: 0 });
    vi.mocked(listNotifications).mockResolvedValue(paginated([]));
    renderWithProviders(<NotificationBell />);

    const trigger = await screen.findByRole("button", { name: /^notifications$/i });
    await userEvent.setup().click(trigger);
    expect(await screen.findByLabelText(/recent notifications/i)).toBeInTheDocument();

    await userEvent.setup().keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByLabelText(/recent notifications/i)).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });
});
