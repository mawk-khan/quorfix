// Shared between the per-bug activity feed (app/bugs/[id]/bug-activity-feed.tsx)
// and the dashboard's cross-bug recent-activity feed (app/recent-activity-feed.tsx)
// — one verb vocabulary, not two copies that can drift.
export const VERB_LABELS: Record<string, string> = {
  created: "created this bug",
  status_changed: "changed status",
  assigned: "assigned",
  unassigned: "unassigned",
  priority_changed: "changed priority",
  severity_changed: "changed severity",
  field_updated: "updated a field",
  tag_added: "added a tag",
  tag_removed: "removed a tag",
  relationship_added: "added a relationship",
  relationship_removed: "removed a relationship",
  archived: "archived this bug",
  restored: "restored this bug",
  comment_added: "added a comment",
  comment_edited: "edited a comment",
  comment_deleted: "deleted a comment",
  comment_redacted: "redacted a comment",
  mention_created: "mentioned a teammate",
  attachment_added: "added an attachment",
  attachment_removed: "removed an attachment",
};

export function actorLabel(
  actor: { first_name: string; last_name: string; email: string } | null,
): string {
  if (!actor) return "System";
  const fullName = `${actor.first_name} ${actor.last_name}`.trim();
  return fullName || actor.email;
}
