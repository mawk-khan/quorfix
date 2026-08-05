import { apiClient } from "./client";
import type { Comment, PaginatedResponse } from "./types";

// Dedicated query-key helpers — every component that reads/invalidates
// comment queries goes through these instead of writing its own ad hoc
// array, matching notificationKeys' shape (frontend/src/lib/api/
// notifications.ts).
export const commentKeys = {
  all: ["comments"] as const,
  lists: (bugId: string) => [...commentKeys.all, bugId] as const,
  list: (bugId: string, page: number) => [...commentKeys.lists(bugId), page] as const,
};

export function listComments(bugId: string, page = 1): Promise<PaginatedResponse<Comment>> {
  const qs = page > 1 ? `?page=${page}` : "";
  return apiClient.get<PaginatedResponse<Comment>>(`/bugs/${bugId}/comments/${qs}`);
}

export function createComment(bugId: string, body: string): Promise<Comment> {
  return apiClient.post<Comment>(`/bugs/${bugId}/comments/`, { body });
}

export function updateComment(bugId: string, commentId: string, body: string): Promise<Comment> {
  return apiClient.patch<Comment>(`/bugs/${bugId}/comments/${commentId}/`, { body });
}

export function deleteComment(bugId: string, commentId: string): Promise<Comment> {
  return apiClient.delete<Comment>(`/bugs/${bugId}/comments/${commentId}/`);
}

export function redactComment(bugId: string, commentId: string): Promise<Comment> {
  return apiClient.post<Comment>(`/bugs/${bugId}/comments/${commentId}/redact/`);
}

// Builds the backend's structured mention source token
// (apps.comments.mentions.MENTION_TOKEN_RE) — the display name is cosmetic
// only, the uuid is the sole source of truth for who was actually mentioned.
export function buildMentionToken(displayName: string, userId: string): string {
  // The backend's regex disallows `[`, `]`, and newlines in the display-name
  // segment — strip them so a name can never accidentally break the token
  // it's embedded in.
  const safeName = displayName.replace(/[[\]\n]/g, "").slice(0, 100);
  return `@[${safeName}](mention:${userId})`;
}
