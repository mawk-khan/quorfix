import { apiClient } from "./client";
import type { ArchivedFilter, PaginatedResponse, Project, ProjectStatus } from "./types";

export interface ListProjectsParams {
  archived?: ArchivedFilter;
  search?: string;
  page?: number;
}

function buildListQuery(params: ListProjectsParams): string {
  const query = new URLSearchParams();
  if (params.archived) query.set("archived", params.archived);
  if (params.search) query.set("search", params.search);
  if (params.page) query.set("page", String(params.page));
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

export function listProjects(
  params: ListProjectsParams = {},
): Promise<PaginatedResponse<Project>> {
  // Unlike listMembers(), this deliberately returns the full paginated
  // envelope rather than flattening it — projects need real pager controls,
  // members today don't.
  return apiClient.get<PaginatedResponse<Project>>(`/projects/${buildListQuery(params)}`);
}

export function getProject(id: string): Promise<Project> {
  return apiClient.get<Project>(`/projects/${id}/`);
}

export interface CreateProjectInput {
  name: string;
  key: string;
  description?: string;
  status?: ProjectStatus;
  lead?: string | null;
}

export function createProject(data: CreateProjectInput): Promise<Project> {
  return apiClient.post<Project>("/projects/", data);
}

export interface UpdateProjectInput {
  name?: string;
  description?: string;
  status?: ProjectStatus;
  lead?: string | null;
}

export function updateProject(id: string, data: UpdateProjectInput): Promise<Project> {
  return apiClient.patch<Project>(`/projects/${id}/`, data);
}

export function archiveProject(id: string): Promise<Project> {
  return apiClient.post<Project>(`/projects/${id}/archive/`);
}

export function restoreProject(id: string): Promise<Project> {
  return apiClient.post<Project>(`/projects/${id}/restore/`);
}
