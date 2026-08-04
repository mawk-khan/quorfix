import { z } from "zod";

export const setupSchema = z.object({
  organization_name: z.string().min(1, "Organization name is required."),
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(8, "Password must be at least 8 characters."),
  first_name: z.string().optional(),
  last_name: z.string().optional(),
});

export type SetupFormValues = z.infer<typeof setupSchema>;
