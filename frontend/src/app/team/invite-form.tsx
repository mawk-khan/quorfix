"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import type { CommunityRole } from "@/lib/api/types";
import { inviteMemberSchema, type InviteMemberFormValues } from "@/lib/validation/invitations";

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
      className="mt-4 flex flex-wrap items-end gap-2"
      aria-label="Invite a member"
    >
      <div>
        <label htmlFor="invite-email" className="block text-sm font-medium">
          Email
        </label>
        <input
          id="invite-email"
          type="email"
          className="mt-1 rounded border px-3 py-2"
          {...register("email")}
        />
        {errors.email && (
          <p role="alert" className="mt-1 text-sm text-red-700">
            {errors.email.message}
          </p>
        )}
      </div>
      <div>
        <label htmlFor="invite-role" className="block text-sm font-medium">
          Role
        </label>
        <select id="invite-role" className="mt-1 rounded border px-2 py-2" {...register("role")}>
          {ROLES.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </select>
      </div>
      <button
        type="submit"
        disabled={isSubmitting}
        className="rounded bg-black px-3 py-2 text-white disabled:opacity-50"
      >
        Invite
      </button>
    </form>
  );
}
