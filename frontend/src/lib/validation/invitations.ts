import { z } from "zod";

export const acceptInvitationSchema = z.object({
  password: z.string().min(8, "Password must be at least 8 characters."),
  first_name: z.string().optional(),
  last_name: z.string().optional(),
});

export type AcceptInvitationFormValues = z.infer<typeof acceptInvitationSchema>;

export const inviteMemberSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  role: z.enum(["administrator", "developer", "qa", "reporter", "viewer"]),
});

export type InviteMemberFormValues = z.infer<typeof inviteMemberSchema>;
