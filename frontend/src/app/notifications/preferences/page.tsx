"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

import { ApiError } from "@/lib/api/client";
import { listNotificationPreferences, notificationKeys, updateNotificationPreference } from "@/lib/api/notifications";
import type { NotificationEventType } from "@/lib/api/types";
import { useSession } from "@/lib/auth/session-provider";

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
      <main className="p-8">
        <p>Loading…</p>
      </main>
    );
  }

  if (!session?.authenticated) {
    return (
      <main className="p-8">
        <p role="alert">You must sign in to view this page.</p>
      </main>
    );
  }

  if (preferencesQuery.isError) {
    return (
      <main className="p-8">
        <p role="alert" className="text-sm text-red-700">
          {describeError(preferencesQuery.error)}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl space-y-6 p-8">
      <div>
        <Link href="/notifications" className="text-sm text-blue-700 underline">
          ← Back to notifications
        </Link>
        <h1 className="mt-2 text-xl font-semibold">Email notification preferences</h1>
        <p className="mt-1 text-sm text-gray-500">
          In-app notifications are always created and cannot be disabled. These toggles control
          email delivery only.
        </p>
      </div>

      <ul className="divide-y rounded border">
        {(preferencesQuery.data ?? []).map((preference) => (
          <li key={preference.event_type} className="flex items-center justify-between gap-3 px-4 py-3">
            <label htmlFor={`notification-preference-${preference.event_type}`} className="text-sm">
              {EVENT_TYPE_LABELS[preference.event_type]}
            </label>
            <input
              id={`notification-preference-${preference.event_type}`}
              type="checkbox"
              checked={preference.email_enabled}
              onChange={(event) =>
                updateMutation.mutate({ eventType: preference.event_type, emailEnabled: event.target.checked })
              }
              aria-label={`Email me: ${EVENT_TYPE_LABELS[preference.event_type]}`}
            />
          </li>
        ))}
      </ul>
    </main>
  );
}
