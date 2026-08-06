import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Notification, PaginatedResponse, Session } from "@/lib/api/types";
import { renderWithProviders } from "@/test-utils";

const replaceMock = vi.fn();
const routerMock = { replace: replaceMock };
let currentSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  usePathname: () => "/notifications",
  useSearchParams: () => currentSearchParams,
}));

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn(),
}));

vi.mock("@/lib/api/notifications", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/api/notifications")>("@/lib/api/notifications");
  return {
    ...actual,
    listNotifications: vi.fn(),
    markNotificationRead: vi.fn(),
    markAllNotificationsRead: vi.fn(),
  };
});

import { getSession } from "@/lib/api/auth";
import { listNotifications, markAllNotificationsRead, markNotificationRead } from "@/lib/api/notifications";
import NotificationsPage from "./page";

function mockSession(): void {
  vi.mocked(getSession).mockResolvedValue({
    authenticated: true,
    role: "developer",
    user: { id: "me", email: "me@example.com", first_name: "Me", last_name: "" },
    organization: { id: "org1", name: "Acme", slug: "acme" },
  } satisfies Session);
}

function paginated(results: Notification[], count = results.length): PaginatedResponse<Notification> {
  return { count, next: null, previous: null, results };
}

const notificationFixture: Notification = {
  id: "n1",
  event_type: "mentioned",
  actor: { id: "u1", email: "actor@example.com", first_name: "Ada", last_name: "Lovelace" },
  bug: { id: "b1", key: "ENG-1", title: "Login broken", status: "new" },
  comment_id: "c1",
  read_at: null,
  email_status: "pending",
  created_at: new Date().toISOString(),
  target_url: "/bugs/b1",
};

describe("NotificationsPage", () => {
  beforeEach(() => {
    currentSearchParams = new URLSearchParams();
    replaceMock.mockClear();
    vi.mocked(listNotifications).mockReset();
    vi.mocked(markNotificationRead).mockReset();
    vi.mocked(markAllNotificationsRead).mockReset();
  });

  it("requires authentication", async () => {
    vi.mocked(getSession).mockResolvedValue({
      authenticated: false,
      role: null,
      user: null,
      organization: null,
    });
    renderWithProviders(<NotificationsPage />);

    expect(await screen.findByRole("heading", { name: /sign in required/i })).toBeInTheDocument();
    expect(screen.getByText(/must sign in to view this page/i)).toBeInTheDocument();
  });

  it("shows an empty state when there are no notifications", async () => {
    mockSession();
    vi.mocked(listNotifications).mockResolvedValueOnce(paginated([]));
    renderWithProviders(<NotificationsPage />);

    expect(await screen.findByText(/no notifications match/i)).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    mockSession();
    vi.mocked(listNotifications).mockRejectedValueOnce(new Error("boom"));
    renderWithProviders(<NotificationsPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/something went wrong/i);
  });

  it("renders notification rows with actor, bug, and unread indicator", async () => {
    mockSession();
    vi.mocked(listNotifications).mockResolvedValueOnce(paginated([notificationFixture]));
    renderWithProviders(<NotificationsPage />);

    expect(await screen.findByText(/ada lovelace mentioned you/i)).toBeInTheDocument();
    expect(screen.getByText(/ENG-1 — Login broken/)).toBeInTheDocument();
    expect(screen.getByText("(unread)")).toBeInTheDocument(); // sr-only, not color-only
  });

  it("updates the URL when the read filter changes", async () => {
    mockSession();
    vi.mocked(listNotifications).mockResolvedValue(paginated([notificationFixture]));
    renderWithProviders(<NotificationsPage />);

    await screen.findByText(/ada lovelace mentioned you/i);
    await userEvent.setup().selectOptions(screen.getByLabelText(/read state/i), "false");

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/notifications?read=false"));
  });

  it("updates the URL when the event type filter changes", async () => {
    mockSession();
    vi.mocked(listNotifications).mockResolvedValue(paginated([notificationFixture]));
    renderWithProviders(<NotificationsPage />);

    await screen.findByText(/ada lovelace mentioned you/i);
    await userEvent.setup().selectOptions(screen.getByLabelText(/event type/i), "mentioned");

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/notifications?event_type=mentioned"));
  });

  it("invalid read query param is treated as no filter rather than crashing", async () => {
    currentSearchParams = new URLSearchParams("read=not-a-valid-value");
    mockSession();
    vi.mocked(listNotifications).mockResolvedValueOnce(paginated([notificationFixture]));
    renderWithProviders(<NotificationsPage />);

    expect(await screen.findByText(/ada lovelace mentioned you/i)).toBeInTheDocument();
    expect(vi.mocked(listNotifications).mock.calls[0]?.[0]).toMatchObject({ read: undefined });
  });

  it("marks a notification read via its own button", async () => {
    mockSession();
    vi.mocked(listNotifications).mockResolvedValue(paginated([notificationFixture]));
    vi.mocked(markNotificationRead).mockResolvedValue({
      ...notificationFixture,
      read_at: new Date().toISOString(),
    });
    renderWithProviders(<NotificationsPage />);

    await screen.findByText(/ada lovelace mentioned you/i);
    await userEvent.setup().click(screen.getByRole("button", { name: /^mark read$/i }));

    await waitFor(() => expect(vi.mocked(markNotificationRead).mock.calls[0]?.[0]).toBe("n1"));
  });

  it("mark all read calls the mutation", async () => {
    mockSession();
    vi.mocked(listNotifications).mockResolvedValue(paginated([notificationFixture]));
    vi.mocked(markAllNotificationsRead).mockResolvedValue({ updated: 1 });
    renderWithProviders(<NotificationsPage />);

    await screen.findByText(/ada lovelace mentioned you/i);
    await userEvent.setup().click(screen.getByRole("button", { name: /^mark all read$/i }));

    await waitFor(() => expect(markAllNotificationsRead).toHaveBeenCalled());
  });

  it("shows pagination controls when there is more than one page", async () => {
    mockSession();
    const many = Array.from({ length: 25 }, (_, i) => ({ ...notificationFixture, id: `n${i}` }));
    vi.mocked(listNotifications).mockResolvedValueOnce(paginated(many, 40));
    renderWithProviders(<NotificationsPage />);

    expect(await screen.findByText(/page 1 of 2/i)).toBeInTheDocument();
  });
});
