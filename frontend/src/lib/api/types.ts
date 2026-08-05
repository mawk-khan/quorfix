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

export type ProjectStatus = "planning" | "active" | "on_hold" | "completed";

export type ArchivedFilter = "true" | "false" | "all";

export interface Project {
  id: string;
  name: string;
  key: string;
  description: string;
  status: ProjectStatus;
  lead: User | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export type BugStatus =
  | "new"
  | "triaged"
  | "assigned"
  | "in_progress"
  | "ready_for_qa"
  | "resolved"
  | "reopened"
  | "closed"
  | "blocked"
  | "duplicate"
  | "cannot_reproduce"
  | "wont_fix"
  | "deferred";

export type BugPriority = "urgent" | "high" | "medium" | "low";

export type BugSeverity = "blocker" | "critical" | "major" | "minor" | "trivial";

export type BugRelationshipType = "duplicate_of" | "duplicated_by" | "blocks" | "blocked_by" | "relates_to";

export interface ProjectRef {
  id: string;
  key: string;
  name: string;
}

export interface Tag {
  id: string;
  name: string;
}

// The list representation — deliberately lean (no description/steps/etc.),
// matching the backend's BugListSerializer, so a page of rows stays cheap.
export interface BugSummary {
  id: string;
  key: string;
  number: number;
  project: ProjectRef;
  title: string;
  status: BugStatus;
  priority: BugPriority;
  severity: BugSeverity;
  reporter: User;
  assignee: User | null;
  due_date: string | null;
  archived_at: string | null;
  version: number;
  is_watching: boolean;
  created_at: string;
  updated_at: string;
}

export interface BugRelationshipRef {
  id: string;
  type: BugRelationshipType;
  bug: { id: string; key: string; title: string; status: BugStatus };
}

// The backend computes these server-side and they are the ONLY source of
// truth for what this viewer may currently do to this bug — the frontend
// must never re-derive them from a hardcoded copy of the workflow/role
// matrix. See BugDetailSerializer.
export interface Bug extends BugSummary {
  description: string;
  steps_to_reproduce: string;
  expected_result: string;
  actual_result: string;
  environment: string;
  category: string;
  resolved_at: string | null;
  closed_at: string | null;
  tags: Tag[];
  watcher_count: number;
  available_transitions: BugStatus[];
  editable_fields: string[];
  can_assign: boolean;
  can_archive: boolean;
  can_manage_relationships: boolean;
  relationships: BugRelationshipRef[];
}

export interface BugVersionConflict {
  code: "bug_version_conflict";
  detail: string;
  bug: Bug;
}

export interface BugActivity {
  id: string;
  verb: string;
  actor: User | null;
  from_value: string;
  to_value: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export type NotificationEventType =
  | "bug_assigned"
  | "mentioned"
  | "comment_added"
  | "status_changed"
  | "bug_reopened";

export type NotificationEmailStatus = "pending" | "sent" | "failed" | "disabled";

export interface NotificationBugRef {
  id: string;
  key: string;
  title: string;
  status: BugStatus;
}

// Matches the backend's explicit allowlist (NotificationSerializer) — never
// carries dedup_key, email_error, organization, or recipient; those are
// deliberately never sent to the client.
export interface Notification {
  id: string;
  event_type: NotificationEventType;
  actor: User | null;
  bug: NotificationBugRef;
  comment_id: string | null;
  read_at: string | null;
  email_status: NotificationEmailStatus;
  created_at: string;
  target_url: string;
}

export interface NotificationPreference {
  event_type: NotificationEventType;
  email_enabled: boolean;
}
