import type { Notification } from "@/lib/api/types";

// Shared between the notification bell and the /notifications page so a
// future 6th event type only ever needs updating in one place.
export const NOTIFICATION_EVENT_LABELS: Record<Notification["event_type"], string> = {
  bug_assigned: "assigned you",
  mentioned: "mentioned you",
  comment_added: "commented",
  status_changed: "changed the status",
  bug_reopened: "reopened",
};

export function notificationActorLabel(actor: Notification["actor"]): string {
  if (!actor) return "System";
  const fullName = `${actor.first_name} ${actor.last_name}`.trim();
  return fullName || actor.email;
}
