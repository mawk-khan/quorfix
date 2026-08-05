import { apiClient } from "./client";
import type {
  ActiveProject,
  AnalyticsSummary,
  DashboardActivity,
  Distributions,
  PaginatedResponse,
  ResolutionTimeEntry,
  TrendPoint,
  Workload,
} from "./types";

// Centralized query-key helpers — every component that reads/invalidates an
// analytics query goes through these, matching the notifications.ts
// convention, so a filter change and a background refetch key off exactly
// the same shape.
export const analyticsKeys = {
  all: ["analytics"] as const,
  summary: (params: DateRangeParams) => [...analyticsKeys.all, "summary", params] as const,
  trends: (params: DateRangeParams) => [...analyticsKeys.all, "trends", params] as const,
  resolutionTime: (params: DateRangeParams) =>
    [...analyticsKeys.all, "resolution-time", params] as const,
  distributions: (params: ProjectOnlyParams) =>
    [...analyticsKeys.all, "distributions", params] as const,
  workload: (params: ProjectOnlyParams) => [...analyticsKeys.all, "workload", params] as const,
  recentActivity: (params: RecentActivityParams) =>
    [...analyticsKeys.all, "recent-activity", params] as const,
  activeProjects: () => [...analyticsKeys.all, "active-projects"] as const,
};

export interface DateRangeParams {
  date_from: string;
  date_to: string;
  project?: string;
}

export interface ProjectOnlyParams {
  project?: string;
}

export interface RecentActivityParams extends ProjectOnlyParams {
  page?: number;
  page_size?: number;
}

function buildQuery(params: object): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params) as [string, string | number | undefined][]) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

export function getSummary(params: DateRangeParams): Promise<AnalyticsSummary> {
  return apiClient.get<AnalyticsSummary>(`/analytics/summary/${buildQuery(params)}`);
}

export function getTrends(params: DateRangeParams): Promise<TrendPoint[]> {
  return apiClient.get<TrendPoint[]>(`/analytics/trends/${buildQuery(params)}`);
}

export function getResolutionTime(params: DateRangeParams): Promise<ResolutionTimeEntry[]> {
  return apiClient.get<ResolutionTimeEntry[]>(`/analytics/resolution-time/${buildQuery(params)}`);
}

export function getDistributions(params: ProjectOnlyParams): Promise<Distributions> {
  return apiClient.get<Distributions>(`/analytics/distributions/${buildQuery(params)}`);
}

export function getWorkload(params: ProjectOnlyParams): Promise<Workload> {
  return apiClient.get<Workload>(`/analytics/workload/${buildQuery(params)}`);
}

export function getRecentActivity(
  params: RecentActivityParams,
): Promise<PaginatedResponse<DashboardActivity>> {
  return apiClient.get<PaginatedResponse<DashboardActivity>>(
    `/analytics/recent-activity/${buildQuery(params)}`,
  );
}

export function getActiveProjects(): Promise<ActiveProject[]> {
  return apiClient.get<ActiveProject[]>("/analytics/active-projects/");
}
