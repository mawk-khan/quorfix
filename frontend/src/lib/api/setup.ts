import { apiClient } from "./client";

export interface SetupPayload {
  organization_name: string;
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
}

export function getSetupStatus() {
  return apiClient.get<{ is_configured: boolean }>("/setup/");
}

export function submitSetup(payload: SetupPayload) {
  return apiClient.post<void>("/setup/", payload);
}
