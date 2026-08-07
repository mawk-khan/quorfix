"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AccessState } from "@/components/access-state";
import { ApiError } from "@/lib/api/client";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  notificationKeys,
} from "@/lib/api/notifications";
import { useSession } from "@/lib/auth/session-provider";
import { NOTIFICATION_EVENT_LABELS, notificationActorLabel } from "@/lib/notifications/format";
import { usePageTitle } from "@/lib/use-page-title";

import { NotificationFilters, type NotificationFiltersValue } from "./notification-filters";
import { PaginationControls } from "./pagination-controls";

function describeError(error: unknown): string {
  if (
    error instanceof ApiError &&
    typeof error.body === "object" &&
    error.body !== null &&
    "detail" in error.body
  ) {
    return String((error.body as { detail: unknown }).detail);
  }
  return "Something went wrong loading notifications.";
}

export default function NotificationsPage() {
  usePageTitle("Notifications");
  return (
    // useSearchParams() opts this page out of static prerendering unless
    // wrapped in Suspense — matches app/bugs/page.tsx and app/projects/page.tsx.
    <Suspense
      fallback={
        <main id="main-content" tabIndex={-1} className="p-8">
          <p>Loading notifications…</p>
        </main>
      }
    >
      <NotificationsPageContent />
    </Suspense>
  );
}

function NotificationsPageContent() {
  const { session, isLoading: sessionLoading } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const filters: NotificationFiltersValue = {
    read:
      (searchParams.get("read") as NotificationFiltersValue["read"] | null) &&
      ["true", "false"].includes(searchParams.get("read")!)
        ? (searchParams.get("read") as NotificationFiltersValue["read"])
        : "",
    event_type: (searchParams.get("event_type") as NotificationFiltersValue["event_type"] | null) ?? "",
  };
  const page = Number(searchParams.get("page") ?? "1") || 1;

  function updateParams(next: Partial<NotificationFiltersValue> & { page?: number }) {
    const params = new URLSearchParams(searchParams.toString());
    const merged = { ...filters, ...next };

    if (merged.read) params.set("read", merged.read);
    else params.delete("read");

    if (merged.event_type) params.set("event_type", merged.event_type);
    else params.delete("event_type");

    const nextPage = next.page ?? 1;
    if (nextPage > 1) params.set("page", String(nextPage));
    else params.delete("page");

    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  const notificationsQuery = useQuery({
    queryKey: notificationKeys.list({
      read: filters.read || undefined,
      event_type: filters.event_type || undefined,
      page,
    }),
    queryFn: () =>
      listNotifications({
        read: filters.read || undefined,
        event_type: filters.event_type || undefined,
        page,
      }),
    enabled: !!session?.authenticated,
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

  if (sessionLoading) {
    return (
      <main id="main-content" tabIndex={-1} className="p-8">
        <p>Loading…</p>
      </main>
    );
  }

  if (!session?.authenticated) {
    return (
      <main id="main-content" tabIndex={-1} className="p-8">
        <AccessState
          heading="Sign in required"
          message="You must sign in to view this page."
          action={{ href: "/sign-in", label: "Go to sign in" }}
        />
      </main>
    );
  }

  const notifications = notificationsQuery.data?.results ?? [];

  return (
    <main id="main-content" tabIndex={-1} className="mx-auto max-w-3xl space-y-6 p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Notifications</h1>
        <div className="flex items-center gap-3">
          <Link href="/notifications/preferences" className="text-sm text-blue-700 underline">
            Email preferences
          </Link>
          <button
            type="button"
            onClick={() => markAllMutation.mutate()}
            disabled={markAllMutation.isPending}
            className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
          >
            Mark all read
          </button>
        </div>
      </div>

      <NotificationFilters value={filters} onChange={(next) => updateParams(next)} />

      {notificationsQuery.isLoading && <p>Loading…</p>}

      {notificationsQuery.isError && (
        <p role="alert" className="text-sm text-red-700">
          {describeError(notificationsQuery.error)}
        </p>
      )}

      {notificationsQuery.data && notifications.length === 0 && (
        <p className="text-sm text-gray-500">No notifications match these filters.</p>
      )}

      {notificationsQuery.data && notifications.length > 0 && (
        <>
          <ul className="divide-y rounded border">
            {notifications.map((notification) => {
              const isUnread = !notification.read_at;
              return (
                <li key={notification.id} className={isUnread ? "bg-blue-50" : ""}>
                  <div className="flex items-center justify-between gap-3 px-4 py-3">
                    <Link
                      href={notification.target_url}
                      className="flex-1 text-sm"
                      onClick={() => {
                        if (isUnread) markReadMutation.mutate(notification.id);
                      }}
                    >
                      <span className={isUnread ? "font-semibold" : ""}>
                        {isUnread && (
                          <span
                            aria-hidden="true"
                            className="mr-1 inline-block h-2 w-2 rounded-full bg-blue-700"
                          />
                        )}
                        {notificationActorLabel(notification.actor)}{" "}
                        {NOTIFICATION_EVENT_LABELS[notification.event_type]}
                        {isUnread && <span className="sr-only"> (unread)</span>}
                      </span>
                      <span className="block text-xs text-gray-500">
                        {notification.bug.key} — {notification.bug.title}
                      </span>
                      <span className="block text-xs text-gray-500">
                        {new Date(notification.created_at).toLocaleString()}
                      </span>
                    </Link>
                    {isUnread && (
                      <button
                        type="button"
                        onClick={() => markReadMutation.mutate(notification.id)}
                        className="shrink-0 text-xs text-blue-700 underline"
                      >
                        Mark read
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          <PaginationControls
            count={notificationsQuery.data.count}
            currentPage={page}
            onPageChange={(nextPage) => updateParams({ page: nextPage })}
          />
        </>
      )}
    </main>
  );
}
