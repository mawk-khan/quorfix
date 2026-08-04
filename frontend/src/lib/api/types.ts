export type CommunityRole = "administrator" | "developer" | "qa" | "reporter" | "viewer";

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
}

export interface Session {
  authenticated: boolean;
  user: User | null;
  organization: Organization | null;
  role: CommunityRole | null;
}

export interface Membership {
  id: string;
  user: User;
  role: CommunityRole;
  joined_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: CommunityRole;
  invited_by: string | null;
  created_at: string;
  expires_at: string;
  invite_url?: string;
}

export interface InvitationPublicDetail {
  organization_name: string;
  email: string;
  role: CommunityRole;
  expires_at: string;
}
