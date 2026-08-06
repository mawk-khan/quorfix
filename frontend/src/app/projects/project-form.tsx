"use client";

import type { FieldErrors, Path, UseFormRegister } from "react-hook-form";

import type { Membership } from "@/lib/api/types";
import { errorProps } from "@/lib/forms/error-props";
import { PROJECT_STATUSES } from "@/lib/validation/projects";

interface ProjectFormFields {
  name: string;
  key?: string;
  description?: string;
  status: string;
  lead?: string;
}

interface ProjectFormProps<T extends ProjectFormFields> {
  mode: "create" | "edit";
  register: UseFormRegister<T>;
  errors: FieldErrors<T>;
  onSubmit: (event: React.FormEvent) => void;
  isSubmitting: boolean;
  members: Membership[];
  submitLabel: string;
}

export function ProjectForm<T extends ProjectFormFields>({
  mode,
  register,
  errors,
  onSubmit,
  isSubmitting,
  members,
  submitLabel,
}: ProjectFormProps<T>) {
  return (
    <form
      onSubmit={onSubmit}
      className="space-y-4"
      aria-label={mode === "create" ? "Create project" : "Edit project"}
    >
      <div>
        <label htmlFor="project-name" className="block text-sm font-medium">
          Name
        </label>
        <input
          id="project-name"
          className="mt-1 w-full rounded border px-3 py-2"
          {...errorProps("project-name", errors.name)}
          {...register("name" as Path<T>)}
        />
        {errors.name && (
          <p id="project-name-error" role="alert" className="mt-1 text-sm text-red-700">
            {errors.name.message as string}
          </p>
        )}
      </div>

      {mode === "create" && (
        <div>
          <label htmlFor="project-key" className="block text-sm font-medium">
            Key
          </label>
          <input
            id="project-key"
            className="mt-1 w-full rounded border px-3 py-2 font-mono uppercase"
            {...errorProps("project-key", errors.key)}
            {...register("key" as Path<T>)}
          />
          {errors.key && (
            <p id="project-key-error" role="alert" className="mt-1 text-sm text-red-700">
              {errors.key.message as string}
            </p>
          )}
        </div>
      )}

      <div>
        <label htmlFor="project-description" className="block text-sm font-medium">
          Description
        </label>
        <textarea
          id="project-description"
          rows={3}
          className="mt-1 w-full rounded border px-3 py-2"
          {...register("description" as Path<T>)}
        />
      </div>

      <div>
        <label htmlFor="project-status" className="block text-sm font-medium">
          Status
        </label>
        <select
          id="project-status"
          className="mt-1 rounded border px-2 py-2"
          {...register("status" as Path<T>)}
        >
          {PROJECT_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status.replace("_", " ")}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="project-lead" className="block text-sm font-medium">
          Lead
        </label>
        <select
          id="project-lead"
          className="mt-1 rounded border px-2 py-2"
          {...register("lead" as Path<T>)}
        >
          <option value="">No lead</option>
          {members.map((member) => (
            <option key={member.id} value={member.user.id}>
              {member.user.first_name} {member.user.last_name} ({member.user.email})
            </option>
          ))}
        </select>
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        className="rounded bg-black px-3 py-2 text-white disabled:opacity-50"
      >
        {submitLabel}
      </button>
    </form>
  );
}
