import { z } from "zod";

export const BUG_PRIORITIES = ["urgent", "high", "medium", "low"] as const;
export const BUG_SEVERITIES = ["blocker", "critical", "major", "minor", "trivial"] as const;

export const createBugSchema = z.object({
  project: z.string().min(1, "Project is required."),
  title: z.string().trim().min(1, "Title is required.").max(255),
  description: z.string().trim().optional(),
  steps_to_reproduce: z.string().trim().optional(),
  expected_result: z.string().trim().optional(),
  actual_result: z.string().trim().optional(),
  environment: z.string().trim().optional(),
  category: z.string().trim().max(100, "Category must be 100 characters or fewer.").optional(),
  priority: z.enum(BUG_PRIORITIES).optional(),
  severity: z.enum(BUG_SEVERITIES).optional(),
  due_date: z.string().optional(),
});

export type CreateBugFormValues = z.infer<typeof createBugSchema>;

// Excludes status/assignee/reporter/project/key/number/version-as-content/
// resolved_at/closed_at/archived_at entirely — this schema can only ever
// produce a payload for the fields the backend's PATCH endpoint accepts as
// editable content. `priority`/`severity` are included because the backend
// itself further restricts them to staff roles at the service layer (a
// reporter's own editable_fields from the API response is what actually
// hides those inputs in the form — see the bug detail page).
export const updateBugSchema = z.object({
  title: z.string().trim().min(1, "Title cannot be blank.").max(255),
  description: z.string().trim().optional(),
  steps_to_reproduce: z.string().trim().optional(),
  expected_result: z.string().trim().optional(),
  actual_result: z.string().trim().optional(),
  environment: z.string().trim().optional(),
  category: z.string().trim().max(100, "Category must be 100 characters or fewer.").optional(),
  due_date: z.string().optional(),
  priority: z.enum(BUG_PRIORITIES).optional(),
  severity: z.enum(BUG_SEVERITIES).optional(),
});

export type UpdateBugFormValues = z.infer<typeof updateBugSchema>;

export const addTagSchema = z.object({
  name: z.string().trim().min(1, "Tag name is required.").max(50, "Tag name must be 50 characters or fewer."),
});

export type AddTagFormValues = z.infer<typeof addTagSchema>;
