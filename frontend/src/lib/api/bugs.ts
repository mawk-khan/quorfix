import { apiClient } from "./client";
import type {
  Bug,
  BugActivity,
  BugPriority,
  BugSeverity,
  BugStatus,
  BugSummary,
  PaginatedResponse,
} from "./types";

// Only these two relationship types are ever created directly through the
// relationships endpoint — duplicate_of is only ever created as a side
// effect of transitionBug(status: "duplicate", duplicate_of: ...), never
// posted here directly (the backend rejects it with InvalidRelationshipType
// if it is).
export type CreatableRelationshipType = "blocks" | "relates_to";

export interface ListBugsParams {
  project?: string;
  status?: BugStatus[];
  priority?: BugPriority;
  severity?: BugSeverity;
  assignee?: string;
  reporter?: string;
  category?: string;
  tags?: string[];
  created_after?: string;
  created_before?: string;
  updated_after?: string;
  updated_before?: string;
  due_after?: string;
  due_before?: string;
  overdue?: boolean;
  unassigned?: boolean;
  watched_by_me?: boolean;
  archived?: "true" | "false" | "all";
  search?: string;
  ordering?: string;
  page?: number;
}

function buildListQuery(params: ListBugsParams): string {
  const query = new URLSearchParams();
  if (params.project) query.set("project", params.project);
  if (params.status?.length) query.set("status", params.status.join(","));
  if (params.priority) query.set("priority", params.priority);
  if (params.severity) query.set("severity", params.severity);
  if (params.assignee) query.set("assignee", params.assignee);
  if (params.reporter) query.set("reporter", params.reporter);
  if (params.category) query.set("category", params.category);
  if (params.tags?.length) query.set("tags", params.tags.join(","));
  if (params.created_after) query.set("created_after", params.created_after);
  if (params.created_before) query.set("created_before", params.created_before);
  if (params.updated_after) query.set("updated_after", params.updated_after);
  if (params.updated_before) query.set("updated_before", params.updated_before);
  if (params.due_after) query.set("due_after", params.due_after);
  if (params.due_before) query.set("due_before", params.due_before);
  if (params.overdue) query.set("overdue", "true");
  if (params.unassigned) query.set("unassigned", "true");
  if (params.watched_by_me) query.set("watched_by_me", "true");
  if (params.archived) query.set("archived", params.archived);
  if (params.search) query.set("search", params.search);
  if (params.ordering) query.set("ordering", params.ordering);
  if (params.page) query.set("page", String(params.page));
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

export function listBugs(params: ListBugsParams = {}): Promise<PaginatedResponse<BugSummary>> {
  return apiClient.get<PaginatedResponse<BugSummary>>(`/bugs/${buildListQuery(params)}`);
}

export function getBug(id: string): Promise<Bug> {
  return apiClient.get<Bug>(`/bugs/${id}/`);
}

export interface CreateBugInput {
  project: string;
  title: string;
  description?: string;
  steps_to_reproduce?: string;
  expected_result?: string;
  actual_result?: string;
  environment?: string;
  category?: string;
  priority?: BugPriority;
  severity?: BugSeverity;
  due_date?: string | null;
}

export function createBug(data: CreateBugInput): Promise<Bug> {
  return apiClient.post<Bug>("/bugs/", data);
}

export interface UpdateBugInput {
  version: number;
  title?: string;
  description?: string;
  steps_to_reproduce?: string;
  expected_result?: string;
  actual_result?: string;
  environment?: string;
  category?: string;
  due_date?: string | null;
  priority?: BugPriority;
  severity?: BugSeverity;
}

// Every mutation below that shares bug state (everything except
// watch/unwatch) requires `version` in its input — the caller must read it
// from the last-fetched Bug and pass it through, so a stale write surfaces
// as a 409 (ApiError with body.code === "bug_version_conflict") instead of
// silently overwriting someone else's change.
export function updateBug(id: string, data: UpdateBugInput): Promise<Bug> {
  return apiClient.patch<Bug>(`/bugs/${id}/`, data);
}

export interface TransitionBugInput {
  status: BugStatus;
  version: number;
  duplicate_of?: string;
  assignee?: string | null;
}

export function transitionBug(id: string, data: TransitionBugInput): Promise<Bug> {
  return apiClient.post<Bug>(`/bugs/${id}/transition/`, data);
}

export function assignBug(id: string, assignee: string | null, version: number): Promise<Bug> {
  return apiClient.post<Bug>(`/bugs/${id}/assign/`, { assignee, version });
}

export function archiveBug(id: string, version: number): Promise<Bug> {
  return apiClient.post<Bug>(`/bugs/${id}/archive/`, { version });
}

export function restoreBug(id: string, version: number): Promise<Bug> {
  return apiClient.post<Bug>(`/bugs/${id}/restore/`, { version });
}

export function addTag(id: string, name: string, version: number): Promise<Bug> {
  return apiClient.post<Bug>(`/bugs/${id}/tags/`, { name, version });
}

export function removeTag(id: string, tagId: string, version: number): Promise<Bug> {
  return apiClient.delete<Bug>(`/bugs/${id}/tags/${tagId}/`, { version });
}

// Watch/unwatch are the one pair of mutations that deliberately do NOT take
// a version — they're per-viewer subscription state, not shared bug
// content, and are safe to call any number of times (idempotent on the
// backend).
export function watchBug(id: string): Promise<Bug> {
  return apiClient.post<Bug>(`/bugs/${id}/watch/`);
}

export function unwatchBug(id: string): Promise<Bug> {
  return apiClient.delete<Bug>(`/bugs/${id}/watch/`);
}

export function listBugActivity(id: string, page = 1): Promise<PaginatedResponse<BugActivity>> {
  const qs = page > 1 ? `?page=${page}` : "";
  return apiClient.get<PaginatedResponse<BugActivity>>(`/bugs/${id}/activity/${qs}`);
}

export function addRelationship(
  id: string,
  relatedBug: string,
  relationshipType: CreatableRelationshipType,
  version: number,
): Promise<Bug> {
  return apiClient.post<Bug>(`/bugs/${id}/relationships/`, {
    related_bug: relatedBug,
    relationship_type: relationshipType,
    version,
  });
}

export function removeRelationship(id: string, relationshipId: string, version: number): Promise<Bug> {
  return apiClient.delete<Bug>(`/bugs/${id}/relationships/${relationshipId}/`, { version });
}
