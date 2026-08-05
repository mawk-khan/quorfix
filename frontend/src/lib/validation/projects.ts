import { z } from "zod";

export const PROJECT_STATUSES = ["planning", "active", "on_hold", "completed"] as const;

const projectKeySchema = z
  .string()
  .trim()
  .toUpperCase()
  .regex(
    /^[A-Z][A-Z0-9]{1,9}$/,
    "Key must be 2-10 characters, start with a letter, and contain only uppercase letters and digits.",
  );

export const createProjectSchema = z.object({
  name: z.string().trim().min(1, "Name is required.").max(255),
  key: projectKeySchema,
  description: z.string().trim().optional(),
  status: z.enum(PROJECT_STATUSES),
  lead: z.string().optional(),
});

export type CreateProjectFormValues = z.infer<typeof createProjectSchema>;

export const updateProjectSchema = z.object({
  name: z.string().trim().min(1, "Name is required.").max(255),
  description: z.string().trim().optional(),
  status: z.enum(PROJECT_STATUSES),
  lead: z.string().optional(),
});

export type UpdateProjectFormValues = z.infer<typeof updateProjectSchema>;
