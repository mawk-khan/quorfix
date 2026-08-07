import type { CommunityRole } from "@/lib/api/types";

export const ROLE_LABELS: Record<CommunityRole, string> = {
  administrator: "Administrator",
  developer: "Developer",
  qa: "QA",
  reporter: "Reporter",
  viewer: "Viewer",
};
