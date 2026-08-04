import { apiClient } from "./client";
import type { Session } from "./types";

export function getSession() {
  return apiClient.get<Session>("/auth/session/");
}

export function login(email: string, password: string) {
  return apiClient.post<void>("/auth/login/", { email, password });
}

export function logout() {
  return apiClient.post<void>("/auth/logout/");
}
