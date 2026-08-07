"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { CommunityRole } from "@/lib/api/types";
import { errorProps } from "@/lib/forms/error-props";
import { inviteMemberSchema, type InviteMemberFormValues } from "@/lib/validation/invitations";

import { ROLE_LABELS } from "./role-labels";

const ROLES: CommunityRole[] = ["administrator", "developer", "qa", "reporter", "viewer"];

interface InviteFormProps {
  onSubmit: (values: InviteMemberFormValues) => void;
  isSubmitting: boolean;
}

export function InviteForm({ onSubmit, isSubmitting }: InviteFormProps) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<InviteMemberFormValues>({ resolver: zodResolver(inviteMemberSchema) });

  return (
    <form
      onSubmit={handleSubmit((values) => {
        onSubmit(values);
        reset();
      })}
      className="flex flex-wrap items-end gap-3"
      aria-label="Invite a member"
    >
      <FormField htmlFor="invite-email" label="Email" error={errors.email}>
        <Input
          id="invite-email"
          type="email"
          autoComplete="email"
          {...errorProps("invite-email", errors.email)}
          {...register("email")}
        />
      </FormField>
      <FormField htmlFor="invite-role" label="Role">
        <Select id="invite-role" className="w-40" {...register("role")}>
          {ROLES.map((role) => (
            <option key={role} value={role}>
              {ROLE_LABELS[role]}
            </option>
          ))}
        </Select>
      </FormField>
      <Button type="submit" loading={isSubmitting}>
        Invite
      </Button>
    </form>
  );
}
