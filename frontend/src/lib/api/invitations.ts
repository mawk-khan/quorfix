import { apiClient } from "./client";
import type { CommunityRole, Invitation, InvitationPublicDetail, PaginatedResponse } from "./types";

export interface CreateInvitationPayload {
  email: string;
  role: CommunityRole;
}

export interface AcceptInvitationPayload {
  password: string;
  first_name?: string;
  last_name?: string;
}

export async function listInvitations(): Promise<Invitation[]> {
  // Same bounded-pagination unwrap as listMembers() — see there for why.
  const response = await apiClient.get<PaginatedResponse<Invitation>>("/invitations/");
  return response.results;
}

export function createInvitation(payload: CreateInvitationPayload) {
  return apiClient.post<Invitation>("/invitations/", payload);
}

export function cancelInvitation(id: string) {
  return apiClient.delete<void>(`/invitations/${id}/`);
}

export function getInvitation(token: string) {
  return apiClient.get<InvitationPublicDetail>(`/invitations/${token}/`);
}

export function acceptInvitation(token: string, payload: AcceptInvitationPayload) {
  return apiClient.post<void>(`/invitations/${token}/accept/`, payload);
}
