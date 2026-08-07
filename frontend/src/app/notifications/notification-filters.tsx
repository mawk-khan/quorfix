"use client";

import { Select } from "@/components/ui/select";
import type { NotificationEventType } from "@/lib/api/types";

const EVENT_TYPE_OPTIONS: { value: NotificationEventType; label: string }[] = [
  { value: "bug_assigned", label: "Bug assigned" },
  { value: "mentioned", label: "Mentioned" },
  { value: "comment_added", label: "Comment added" },
  { value: "status_changed", label: "Status changed" },
  { value: "bug_reopened", label: "Bug reopened" },
];

export interface NotificationFiltersValue {
  read: "" | "true" | "false";
  event_type: "" | NotificationEventType;
}

interface NotificationFiltersProps {
  value: NotificationFiltersValue;
  onChange: (next: Partial<NotificationFiltersValue>) => void;
}

export function NotificationFilters({ value, onChange }: NotificationFiltersProps) {
  return (
    <div className="flex flex-wrap items-end gap-4">
      <div>
        <label htmlFor="notification-read-filter" className="block text-sm font-medium text-text-primary">
          Read state
        </label>
        <Select
          id="notification-read-filter"
          value={value.read}
          onChange={(event) => onChange({ read: event.target.value as NotificationFiltersValue["read"] })}
          className="mt-1.5 w-36"
        >
          <option value="">All</option>
          <option value="false">Unread</option>
          <option value="true">Read</option>
        </Select>
      </div>

      <div>
        <label htmlFor="notification-event-type-filter" className="block text-sm font-medium text-text-primary">
          Event type
        </label>
        <Select
          id="notification-event-type-filter"
          value={value.event_type}
          onChange={(event) =>
            onChange({ event_type: event.target.value as NotificationFiltersValue["event_type"] })
          }
          className="mt-1.5 w-48"
        >
          <option value="">Any</option>
          {EVENT_TYPE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </div>
    </div>
  );
}
