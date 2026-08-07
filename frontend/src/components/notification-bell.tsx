"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
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
  const panelId = useId();

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
        aria-controls={open ? panelId : undefined}
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"}
        onClick={() => setOpen((value) => !value)}
        className="relative flex size-10 items-center justify-center rounded-field text-text-secondary hover:bg-page hover:text-text-primary"
      >
        <Bell aria-hidden="true" className="size-5" />
        {unreadCount > 0 && (
          <span
            aria-hidden="true"
            className="absolute right-1.5 top-1.5 flex min-w-[16px] items-center justify-center rounded-full bg-danger px-1 py-px text-[10px] font-semibold leading-none text-white"
          >
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          id={panelId}
          role="region"
          aria-label="Recent notifications"
          // Below sm: the bell isn't the top bar's rightmost element ("Sign
          // out" sits further right), so a fixed-width dropdown anchored to
          // its own right-0 can run past the viewport's left edge on narrow
          // screens — pinned to the viewport as a near-full-width sheet
          // instead. At sm and up there's enough room for the normal
          // anchored dropdown.
          className="fixed inset-x-4 top-16 z-10 rounded-card border border-border bg-surface shadow-md sm:absolute sm:inset-x-auto sm:right-0 sm:top-auto sm:mt-2 sm:w-80"
        >
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <span className="text-sm font-semibold text-text-primary">Notifications</span>
            <button
              type="button"
              onClick={() => markAllMutation.mutate()}
              disabled={markAllMutation.isPending || unreadCount === 0}
              className="text-xs font-medium text-primary underline disabled:opacity-50 disabled:no-underline"
            >
              Mark all read
            </button>
          </div>

          {dropdownQuery.isLoading && <p className="p-4 text-sm text-text-secondary">Loading…</p>}

          {dropdownQuery.isError && (
            <p role="alert" className="p-4 text-sm text-danger">
              Could not load notifications.
            </p>
          )}

          {dropdownQuery.data && dropdownQuery.data.results.length === 0 && (
            <EmptyState icon={Bell} title="No notifications yet" />
          )}

          {dropdownQuery.data && dropdownQuery.data.results.length > 0 && (
            <ul className="max-h-96 divide-y divide-border overflow-y-auto">
              {dropdownQuery.data.results.map((notification) => (
                <li key={notification.id}>
                  <button
                    type="button"
                    onClick={() => handleNotificationClick(notification)}
                    className={`block w-full px-4 py-2.5 text-left text-sm hover:bg-page ${
                      notification.read_at ? "" : "bg-primary-subtle/40 font-semibold"
                    }`}
                  >
                    <span className="block text-text-primary">
                      {!notification.read_at && (
                        <span aria-hidden="true" className="mr-1.5 inline-block size-1.5 rounded-full bg-primary" />
                      )}
                      {notificationActorLabel(notification.actor)}{" "}
                      {NOTIFICATION_EVENT_LABELS[notification.event_type]}
                      {!notification.read_at && <span className="sr-only"> (unread)</span>}
                    </span>
                    <span className="block text-xs font-normal text-text-secondary">{notification.bug.key}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="border-t border-border px-4 py-2.5 text-center">
            <Link
              href="/notifications"
              className="text-sm font-medium text-primary underline"
              onClick={() => setOpen(false)}
            >
              View all
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
