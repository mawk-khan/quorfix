import { apiClient } from "./client";
import type { CommunityRole, Membership, PaginatedResponse } from "./types";

export interface ListMembersParams {
  // Passed straight through to the backend's existing page_size query param
  // (BoundedPageNumberPagination, capped at 100) — e.g. the mention picker
  // requests a larger single page than the 25-row UI default so client-side
  // filtering has Community's realistic full team to search over.
  page_size?: number;
}

export async function listMembers(params: ListMembersParams = {}): Promise<Membership[]> {
  // The backend paginates (bounded server-side pagination); Community's
  // realistic team sizes fit comfortably on one page, so this unwraps to a
  // flat array rather than exposing pagination controls in the UI yet.
  const query = params.page_size ? `?page_size=${params.page_size}` : "";
  const response = await apiClient.get<PaginatedResponse<Membership>>(`/members/${query}`);
  return response.results;
}

export function updateMemberRole(id: string, role: CommunityRole) {
  return apiClient.patch<Membership>(`/members/${id}/`, { role });
}

export function removeMember(id: string) {
  return apiClient.delete<void>(`/members/${id}/`);
}
