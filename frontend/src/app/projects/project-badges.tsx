import { Badge, type BadgeTone } from "@/components/ui/badge";
import type { ProjectStatus } from "@/lib/api/types";

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  planning: "Planning",
  active: "Active",
  on_hold: "On hold",
  completed: "Completed",
};

const PROJECT_STATUS_TONES: Record<ProjectStatus, BadgeTone> = {
  planning: "blue",
  active: "green",
  on_hold: "amber",
  completed: "neutral",
};

export function ProjectStatusBadge({ status }: { status: ProjectStatus }) {
  return <Badge tone={PROJECT_STATUS_TONES[status]}>{PROJECT_STATUS_LABELS[status]}</Badge>;
}
