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

export type CommentStatus = "active" | "deleted" | "redacted";

export interface Mention {
  id: string;
  mentioned_user: User;
}

// can_edit/can_delete/can_redact are authoritative UI hints computed
// server-side (apps.comments.serializers.CommentSerializer) — never
// re-derived from a client-side copy of the role/edit-window matrix, and
// never trusted in place of the backend's own 403/409 on the actual mutation.
export interface Comment {
  id: string;
  author: User;
  body: string;
  status: CommentStatus;
  mentions: Mention[];
  edited_at: string | null;
  deleted_at: string | null;
  redacted_at: string | null;
  can_edit: boolean;
  can_delete: boolean;
  can_redact: boolean;
  created_at: string;
  updated_at: string;
}

export type AttachmentStatus = "pending" | "uploaded" | "failed";

export type ScanStatus = "not_scanned" | "pending" | "clean" | "infected";

// can_remove is a UI hint only (apps.attachments.serializers.
// AttachmentSerializer.get_can_remove) — it does not factor in archive
// state, so the backend's actual 403/409 on removal remains authoritative.
export interface Attachment {
  id: string;
  uploaded_by: User;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  status: AttachmentStatus;
  scan_status: ScanStatus;
  uploaded_at: string | null;
  removed_at: string | null;
  can_remove: boolean;
  created_at: string;
}

export interface AttachmentUploadInstructions {
  method: "PUT";
  url: string;
}

export interface AttachmentInitiateResponse {
  attachment: Attachment;
  upload: AttachmentUploadInstructions;
}

// -- analytics dashboard ----------------------------------------------------
//
// Every number here is authoritative — computed server-side in
// apps.analytics.selectors. The frontend never recomputes a total,
// percentage, or duration from raw data; it only formats what the backend
// already returned. See docs/ACCESS_AND_TESTING.md for which sections
// respect the date-range filter and which are current-state snapshots.

export interface AnalyticsSummary {
  open_bugs: number;
  overdue_bugs: number;
  new_bugs: number;
  resolved_bugs: number;
}

export interface TrendPoint {
  date: string;
  created: number;
  resolved: number;
}

export interface ResolutionTimeEntry {
  priority: BugPriority;
  // Null means no bug at this priority currently has a resolution in
  // range — never rendered as zero, which would be a real (very fast)
  // resolution time instead of "no data".
  average_seconds: number | null;
}

export interface StatusCount {
  status: BugStatus;
  count: number;
}

export interface SeverityCount {
  severity: BugSeverity;
  count: number;
}

export interface Distributions {
  status: StatusCount[];
  severity: SeverityCount[];
}

export interface WorkloadEntry {
  user_id: string;
  name: string;
  role: CommunityRole;
  count: number;
}

export interface Workload {
  eligible: WorkloadEntry[];
  unassigned: number;
  // Bugs whose assignee's *current* role is no longer eligible for
  // assignment (demoted, not removed — a removed member's bugs are
  // cleared to unassigned automatically). Never merged into `eligible` or
  // `unassigned`: hiding these would let a bug silently disappear from
  // every workload view.
  needs_reassignment: WorkloadEntry[];
}

export interface ActiveProject {
  id: string;
  key: string;
  name: string;
  status: ProjectStatus;
  total_bugs: number;
  open_bugs: number;
}

export interface DashboardActivityBugRef {
  id: string;
  key: string;
  title: string;
}

// Cross-bug activity feed row — deliberately omits raw `metadata` (unlike
// BugActivity above, which is scoped to one bug's own detail page).
export interface DashboardActivity {
  id: string;
  bug: DashboardActivityBugRef;
  project: ProjectRef;
  actor: User | null;
  verb: string;
  from_value: string;
  to_value: string;
  created_at: string;
}
