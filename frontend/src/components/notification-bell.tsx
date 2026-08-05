"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  getUnreadCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  notificationKeys,
} from "@/lib/api/notifications";
import type { Notification } from "@/lib/api/types";
import { NOTIFICATION_EVENT_LABELS, notificationActorLabel } from "@/lib/notifications/format";

// A small first page only — the dropdown is a preview, never the full
// notification history (that's what /notifications is for).
const DROPDOWN_PAGE_SIZE = 5;

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const router = useRouter();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Both queries key off notificationKeys — the same keys the /notifications
  // and /notifications/preferences pages use, so mutations anywhere
  // invalidate everywhere. Only one NotificationBell is ever mounted (it
  // lives in AppShell, itself mounted once in the root layout), and even if
  // that were ever violated, TanStack Query dedupes subscribers sharing an
  // identical query key into a single underlying fetch/interval — it does
  // not run one polling timer per mounted component.
  const unreadQuery = useQuery({
    queryKey: notificationKeys.unreadCount(),
    queryFn: getUnreadCount,
    refetchInterval: 30_000,
  });

  const dropdownQuery = useQuery({
    queryKey: notificationKeys.list({ page: 1, page_size: DROPDOWN_PAGE_SIZE }),
    queryFn: () => listNotifications({ page: 1, page_size: DROPDOWN_PAGE_SIZE }),
    enabled: open, // fetched only once the dropdown is actually opened
  });

  function invalidateNotificationCaches() {
    queryClient.invalidateQueries({ queryKey: notificationKeys.unreadCount() });
    queryClient.invalidateQueries({ queryKey: notificationKeys.lists() });
  }

  const markReadMutation = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: invalidateNotificationCaches,
  });

  const markAllMutation = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: invalidateNotificationCaches,
  });

  useEffect(() => {
    if (!open) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    function onClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onClickOutside);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onClickOutside);
    };
  }, [open]);

  const unreadCount = unreadQuery.data?.count ?? 0;

  function handleNotificationClick(notification: Notification) {
    // Fire-and-forget: navigation must never wait on this mutation, and a
    // failed mark-read must never block the user from reaching the bug they
    // clicked. If it fails, the notification simply stays unread until the
    // next successful mark-read/mark-all-read.
    if (!notification.read_at) {
      markReadMutation.mutate(notification.id);
    }
    setOpen(false);
    router.push(notification.target_url);
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"}
        onClick={() => setOpen((value) => !value)}
        className="relative rounded border px-3 py-1.5 text-sm"
      >
        Notifications
        {unreadCount > 0 && (
          <span
            aria-hidden="true"
            className="ml-1 rounded-full bg-red-700 px-1.5 py-0.5 text-xs font-semibold text-white"
          >
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          aria-label="Recent notifications"
          className="absolute right-0 z-10 mt-2 w-80 rounded border bg-white shadow-lg"
        >
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="text-sm font-medium">Notifications</span>
            <button
              type="button"
              onClick={() => markAllMutation.mutate()}
              disabled={markAllMutation.isPending || unreadCount === 0}
              className="text-xs text-blue-700 underline disabled:opacity-50 disabled:no-underline"
            >
              Mark all read
            </button>
          </div>

          {dropdownQuery.isLoading && <p className="p-3 text-sm text-gray-500">Loading…</p>}

          {dropdownQuery.isError && (
            <p role="alert" className="p-3 text-sm text-red-700">
              Could not load notifications.
            </p>
          )}

          {dropdownQuery.data && dropdownQuery.data.results.length === 0 && (
            <p className="p-3 text-sm text-gray-500">No notifications yet.</p>
          )}

          {dropdownQuery.data && dropdownQuery.data.results.length > 0 && (
            <ul className="max-h-96 overflow-y-auto">
              {dropdownQuery.data.results.map((notification) => (
                <li key={notification.id} className="border-b last:border-b-0">
                  <button
                    type="button"
                    onClick={() => handleNotificationClick(notification)}
                    className={`block w-full px-3 py-2 text-left text-sm hover:bg-gray-50 ${
                      notification.read_at ? "" : "font-semibold"
                    }`}
                  >
                    <span className="block">
                      {!notification.read_at && (
                        <span
                          aria-hidden="true"
                          className="mr-1 inline-block h-2 w-2 rounded-full bg-blue-700"
                        />
                      )}
                      {notificationActorLabel(notification.actor)}{" "}
                      {NOTIFICATION_EVENT_LABELS[notification.event_type]}
                      {!notification.read_at && <span className="sr-only"> (unread)</span>}
                    </span>
                    <span className="block text-xs text-gray-500">{notification.bug.key}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="border-t px-3 py-2 text-center">
            <Link href="/notifications" className="text-sm text-blue-700 underline" onClick={() => setOpen(false)}>
              View all
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
