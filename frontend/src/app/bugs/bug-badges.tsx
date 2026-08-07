import { Badge, type BadgeTone } from "@/components/ui/badge";
import type { BugPriority, BugSeverity, BugStatus } from "@/lib/api/types";

// Status is never communicated by color alone — every badge below pairs a
// color with its own text label, so the information survives for
// colorblind users and in any context where color is stripped (print,
// high-contrast mode, screen readers already get the text either way).

export const STATUS_LABELS: Record<BugStatus, string> = {
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

const STATUS_TONES: Record<BugStatus, BadgeTone> = {
  new: "neutral",
  triaged: "blue",
  assigned: "indigo",
  in_progress: "blue",
  ready_for_qa: "violet",
  resolved: "green",
  reopened: "amber",
  blocked: "red",
  closed: "neutral",
  duplicate: "purple",
  cannot_reproduce: "neutral",
  wont_fix: "neutral",
  deferred: "neutral",
};

export function StatusBadge({ status }: { status: BugStatus }) {
  return <Badge tone={STATUS_TONES[status]}>{STATUS_LABELS[status]}</Badge>;
}

export const PRIORITY_LABELS: Record<BugPriority, string> = {
  urgent: "Urgent",
  high: "High",
  medium: "Medium",
  low: "Low",
};

const PRIORITY_TONES: Record<BugPriority, BadgeTone> = {
  urgent: "red",
  high: "orange",
  medium: "amber",
  low: "neutral",
};

export function PriorityBadge({ priority }: { priority: BugPriority }) {
  return <Badge tone={PRIORITY_TONES[priority]}>{PRIORITY_LABELS[priority]} priority</Badge>;
}

export const SEVERITY_LABELS: Record<BugSeverity, string> = {
  blocker: "Blocker",
  critical: "Critical",
  major: "Major",
  minor: "Minor",
  trivial: "Trivial",
};

const SEVERITY_TONES: Record<BugSeverity, BadgeTone> = {
  blocker: "red",
  critical: "rose",
  major: "purple",
  minor: "blue",
  trivial: "neutral",
};

export function SeverityBadge({ severity }: { severity: BugSeverity }) {
  return <Badge tone={SEVERITY_TONES[severity]}>{SEVERITY_LABELS[severity]}</Badge>;
}
