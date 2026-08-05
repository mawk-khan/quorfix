import { apiClient } from "./client";
import type { Notification, NotificationEventType, NotificationPreference, PaginatedResponse } from "./types";

// Centralized query-key helpers — every component that reads/invalidates
// notification queries goes through these instead of writing its own ad hoc
// string array, so a bell-mount invalidation and the /notifications page's
// own query are guaranteed to key off exactly the same shape.
export const notificationKeys = {
  all: ["notifications"] as const,
  lists: () => [...notificationKeys.all, "list"] as const,
  list: (filters: ListNotificationsParams) => [...notificationKeys.lists(), filters] as const,
  unreadCount: () => [...notificationKeys.all, "unread-count"] as const,
  preferences: () => [...notificationKeys.all, "preferences"] as const,
};

export interface ListNotificationsParams {
  read?: "true" | "false";
  event_type?: NotificationEventType;
  page?: number;
  // Lets the bell's dropdown ask for a small page (e.g. 5) instead of the
  // BoundedPageNumberPagination default of 25 — the dropdown must never
  // pull the full notification history just to show a short preview.
  page_size?: number;
}

function buildListQuery(params: ListNotificationsParams): string {
  const query = new URLSearchParams();
  if (params.read) query.set("read", params.read);
  if (params.event_type) query.set("event_type", params.event_type);
  if (params.page) query.set("page", String(params.page));
  if (params.page_size) query.set("page_size", String(params.page_size));
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

export function listNotifications(
  params: ListNotificationsParams = {},
): Promise<PaginatedResponse<Notification>> {
  return apiClient.get<PaginatedResponse<Notification>>(`/notifications/${buildListQuery(params)}`);
}

export function getUnreadCount(): Promise<{ count: number }> {
  return apiClient.get<{ count: number }>("/notifications/unread-count/");
}

export function markNotificationRead(id: string): Promise<Notification> {
  return apiClient.post<Notification>(`/notifications/${id}/read/`);
}

export function markAllNotificationsRead(): Promise<{ updated: number }> {
  return apiClient.post<{ updated: number }>("/notifications/mark-all-read/");
}

export function listNotificationPreferences(): Promise<NotificationPreference[]> {
  return apiClient.get<NotificationPreference[]>("/notifications/preferences/");
}

export function updateNotificationPreference(
  eventType: NotificationEventType,
  emailEnabled: boolean,
): Promise<NotificationPreference> {
  return apiClient.patch<NotificationPreference>(`/notifications/preferences/${eventType}/`, {
    email_enabled: emailEnabled,
  });
}
