"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

import { ArrowLeft } from "lucide-react";

import { AccessState } from "@/components/access-state";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { listNotificationPreferences, notificationKeys, updateNotificationPreference } from "@/lib/api/notifications";
import type { NotificationEventType } from "@/lib/api/types";
import { useSession } from "@/lib/auth/session-provider";
import { usePageTitle } from "@/lib/use-page-title";

const EVENT_TYPE_LABELS: Record<NotificationEventType, string> = {
  bug_assigned: "A bug is assigned to you",
  mentioned: "You are mentioned in a comment",
  comment_added: "Someone comments on a bug you watch",
  status_changed: "A bug you watch changes status",
  bug_reopened: "A bug you watch is reopened",
};

function describeError(error: unknown): string {
  if (
    error instanceof ApiError &&
    typeof error.body === "object" &&
    error.body !== null &&
    "detail" in error.body
  ) {
    return String((error.body as { detail: unknown }).detail);
  }
  return "Something went wrong loading notification preferences.";
}

export default function NotificationPreferencesPage() {
  usePageTitle("Notification preferences");
  const { session, isLoading: sessionLoading } = useSession();
  const queryClient = useQueryClient();

  const preferencesQuery = useQuery({
    queryKey: notificationKeys.preferences(),
    queryFn: listNotificationPreferences,
    enabled: !!session?.authenticated,
  });

  const updateMutation = useMutation({
    mutationFn: ({ eventType, emailEnabled }: { eventType: NotificationEventType; emailEnabled: boolean }) =>
      updateNotificationPreference(eventType, emailEnabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: notificationKeys.preferences() }),
  });

  if (sessionLoading || preferencesQuery.isLoading) {
    return (
      <main id="main-content" tabIndex={-1} className="mx-auto max-w-2xl space-y-6 p-8">
        <Skeleton className="h-64" />
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

  if (preferencesQuery.isError) {
    return (
      <main id="main-content" tabIndex={-1} className="p-8">
        <p role="alert" className="text-sm text-danger">
          {describeError(preferencesQuery.error)}
        </p>
      </main>
    );
  }

  return (
    <main id="main-content" tabIndex={-1} className="mx-auto max-w-2xl space-y-6 p-8">
      <div>
        <Link
          href="/notifications"
          className="inline-flex items-center gap-1 text-sm text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft aria-hidden="true" className="size-4" />
          Back to notifications
        </Link>
      </div>

      <PageHeader
        title="Email notification preferences"
        description="In-app notifications are always created and cannot be disabled. These toggles control email delivery only."
      />

      <Card>
        <ul className="divide-y divide-border">
          {(preferencesQuery.data ?? []).map((preference) => (
            <li key={preference.event_type} className="flex items-center justify-between gap-3 px-5 py-3.5">
              <label
                htmlFor={`notification-preference-${preference.event_type}`}
                className="text-sm text-text-primary"
              >
                {EVENT_TYPE_LABELS[preference.event_type]}
              </label>
              <Checkbox
                id={`notification-preference-${preference.event_type}`}
                checked={preference.email_enabled}
                onChange={(event) =>
                  updateMutation.mutate({ eventType: preference.event_type, emailEnabled: event.target.checked })
                }
                aria-label={`Email me: ${EVENT_TYPE_LABELS[preference.event_type]}`}
              />
            </li>
          ))}
        </ul>
      </Card>
    </main>
  );
}
