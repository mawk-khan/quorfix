"use client";

import type { FieldErrors, Path, UseFormRegister } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { Membership } from "@/lib/api/types";
import { errorProps } from "@/lib/forms/error-props";
import { PROJECT_STATUSES } from "@/lib/validation/projects";

import { PROJECT_STATUS_LABELS } from "./project-badges";

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
      <FormField htmlFor="project-name" label="Name" required error={errors.name?.message as string}>
        <Input id="project-name" {...errorProps("project-name", errors.name)} {...register("name" as Path<T>)} />
      </FormField>

      {mode === "create" && (
        <FormField htmlFor="project-key" label="Key" required error={errors.key?.message as string}>
          <Input
            id="project-key"
            className="font-mono uppercase"
            {...errorProps("project-key", errors.key)}
            {...register("key" as Path<T>)}
          />
        </FormField>
      )}

      <FormField htmlFor="project-description" label="Description" error={errors.description?.message as string}>
        <Textarea id="project-description" rows={3} {...register("description" as Path<T>)} />
      </FormField>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField htmlFor="project-status" label="Status">
          <Select id="project-status" {...register("status" as Path<T>)}>
            {PROJECT_STATUSES.map((status) => (
              <option key={status} value={status}>
                {PROJECT_STATUS_LABELS[status]}
              </option>
            ))}
          </Select>
        </FormField>

        <FormField htmlFor="project-lead" label="Lead">
          <Select id="project-lead" {...register("lead" as Path<T>)}>
            <option value="">No lead</option>
            {members.map((member) => (
              <option key={member.id} value={member.user.id}>
                {member.user.first_name} {member.user.last_name} ({member.user.email})
              </option>
            ))}
          </Select>
        </FormField>
      </div>

      <Button type="submit" loading={isSubmitting}>
        {submitLabel}
      </Button>
    </form>
  );
}
