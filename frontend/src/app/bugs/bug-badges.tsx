import type { BugPriority, BugSeverity, BugStatus } from "@/lib/api/types";

// Status is never communicated by color alone — every badge below pairs a
// color with its own text label, so the information survives for
// colorblind users and in any context where color is stripped (print,
// high-contrast mode, screen readers already get the text either way).

const STATUS_LABELS: Record<BugStatus, string> = {
  new: "New",
  triaged: "Triaged",
  assigned: "Assigned",
  in_progress: "In progress",
  ready_for_qa: "Ready for QA",
  resolved: "Resolved",
  reopened: "Reopened",
  closed: "Closed",
  blocked: "Blocked",
  duplicate: "Duplicate",
  cannot_reproduce: "Cannot reproduce",
  wont_fix: "Won't fix",
  deferred: "Deferred",
};

export function StatusBadge({ status }: { status: BugStatus }) {
  return (
    <span className="inline-block rounded border px-2 py-0.5 text-xs font-medium">
      {STATUS_LABELS[status]}
    </span>
  );
}

const PRIORITY_LABELS: Record<BugPriority, string> = {
  urgent: "Urgent",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export function PriorityBadge({ priority }: { priority: BugPriority }) {
  return (
    <span className="inline-block rounded border px-2 py-0.5 text-xs font-medium">
      {PRIORITY_LABELS[priority]} priority
    </span>
  );
}

const SEVERITY_LABELS: Record<BugSeverity, string> = {
  blocker: "Blocker",
  critical: "Critical",
  major: "Major",
  minor: "Minor",
  trivial: "Trivial",
};

export function SeverityBadge({ severity }: { severity: BugSeverity }) {
  return (
    <span className="inline-block rounded border px-2 py-0.5 text-xs font-medium">
      {SEVERITY_LABELS[severity]}
    </span>
  );
}
