"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Bell } from "lucide-react";

import { AccessState } from "@/components/access-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { formatDateTime } from "@/lib/dashboard/format";
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
    <main id="main-content" tabIndex={-1} className="mx-auto max-w-4xl space-y-6 p-8">
      <PageHeader
        title="Notifications"
        action={
          <div className="flex items-center gap-3">
            <Link
              href="/notifications/preferences"
              className="text-sm font-medium text-primary underline"
            >
              Email preferences
            </Link>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => markAllMutation.mutate()}
              disabled={markAllMutation.isPending}
            >
              Mark all read
            </Button>
          </div>
        }
      />

      <Card>
        <div className="border-b border-border p-5">
          <NotificationFilters value={filters} onChange={(next) => updateParams(next)} />
        </div>

        {notificationsQuery.isLoading && (
          <div className="p-5">
            <Skeleton className="h-64" />
          </div>
        )}

        {notificationsQuery.isError && (
          <div className="p-5">
            <p role="alert" className="text-sm text-danger">
              {describeError(notificationsQuery.error)}
            </p>
          </div>
        )}

        {notificationsQuery.data && notifications.length === 0 && (
          <EmptyState icon={Bell} title="No notifications match these filters" />
        )}

        {notificationsQuery.data && notifications.length > 0 && (
          <>
            <ul className="divide-y divide-border">
              {notifications.map((notification) => {
                const isUnread = !notification.read_at;
                return (
                  <li key={notification.id} className={isUnread ? "bg-primary-subtle/40" : ""}>
                    <div className="flex items-center justify-between gap-3 px-5 py-3">
                      <Link
                        href={notification.target_url}
                        className="min-w-0 flex-1 text-sm"
                        onClick={() => {
                          if (isUnread) markReadMutation.mutate(notification.id);
                        }}
                      >
                        <span className={isUnread ? "font-semibold text-text-primary" : "text-text-primary"}>
                          {isUnread && (
                            <span aria-hidden="true" className="mr-1.5 inline-block size-1.5 rounded-full bg-primary" />
                          )}
                          {notificationActorLabel(notification.actor)}{" "}
                          {NOTIFICATION_EVENT_LABELS[notification.event_type]}
                          {isUnread && <span className="sr-only"> (unread)</span>}
                        </span>
                        <span className="block text-xs text-text-secondary">
                          {notification.bug.key} — {notification.bug.title}
                        </span>
                        <span className="block text-xs text-text-secondary">
                          {formatDateTime(notification.created_at)}
                        </span>
                      </Link>
                      {isUnread && (
                        <button
                          type="button"
                          onClick={() => markReadMutation.mutate(notification.id)}
                          className="shrink-0 text-xs font-medium text-primary underline"
                        >
                          Mark read
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
            <div className="border-t border-border p-4">
              <PaginationControls
                count={notificationsQuery.data.count}
                currentPage={page}
                onPageChange={(nextPage) => updateParams({ page: nextPage })}
              />
            </div>
          </>
        )}
      </Card>
    </main>
  );
}
