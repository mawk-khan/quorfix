import { apiClient } from "./client";
import type { CommunityRole, Session } from "./types";

export function getSession() {
  return apiClient.get<Session>("/auth/session/");
}

export function login(email: string, password: string) {
  return apiClient.post<void>("/auth/login/", { email, password });
}

// Demo-only "Quick Access" login (apps.accounts.views.DemoLoginView) — never
// sends or receives a password. 404s if the backend's QUORFIX_DEMO_MODE is
// disabled; callers gate on session.demo_mode before ever showing UI that
// would call this.
export function demoLogin(role: CommunityRole) {
  return apiClient.post<void>("/auth/demo-login/", { role });
}

export function logout() {
  return apiClient.post<void>("/auth/logout/");
}
