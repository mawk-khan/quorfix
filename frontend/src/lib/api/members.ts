import { apiClient } from "./client";
import type { CommunityRole, Membership, PaginatedResponse } from "./types";

export async function listMembers(): Promise<Membership[]> {
  // The backend paginates (bounded server-side pagination); Community's
  // realistic team sizes fit comfortably on one page, so this unwraps to a
  // flat array rather than exposing pagination controls in the UI yet.
  const response = await apiClient.get<PaginatedResponse<Membership>>("/members/");
  return response.results;
}

export function updateMemberRole(id: string, role: CommunityRole) {
  return apiClient.patch<Membership>(`/members/${id}/`, { role });
}

export function removeMember(id: string) {
  return apiClient.delete<void>(`/members/${id}/`);
}
