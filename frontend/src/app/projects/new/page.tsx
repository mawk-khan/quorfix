"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "@/lib/api/client";
import { listMembers } from "@/lib/api/members";
import { createProject } from "@/lib/api/projects";
import { useSession } from "@/lib/auth/session-provider";
import { createProjectSchema, type CreateProjectFormValues } from "@/lib/validation/projects";

import { ProjectForm } from "../project-form";

function describeError(error: unknown): string {
  if (
    error instanceof ApiError &&
    typeof error.body === "object" &&
    error.body !== null
  ) {
    const body = error.body as Record<string, unknown>;
    if ("detail" in body) return String(body.detail);
    if ("key" in body && Array.isArray(body.key)) return String(body.key[0]);
    if ("lead" in body && Array.isArray(body.lead)) return String(body.lead[0]);
  }
  return "Something went wrong creating the project.";
}

export default function NewProjectPage() {
  const { session, isLoading: sessionLoading } = useSession();
  const isAdmin = session?.role === "administrator";
  const router = useRouter();
  const queryClient = useQueryClient();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const membersQuery = useQuery({
    queryKey: ["members"],
    queryFn: listMembers,
    enabled: isAdmin,
  });

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CreateProjectFormValues>({
    resolver: zodResolver(createProjectSchema),
    defaultValues: { status: "active" },
  });

  const createMutation = useMutation({
    mutationFn: (values: CreateProjectFormValues) =>
      createProject({
        name: values.name,
        key: values.key,
        description: values.description || "",
        status: values.status,
        lead: values.lead || null,
      }),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ["projects", "list"] });
      router.push(`/projects/${project.id}`);
    },
    onError: (error) => setSubmitError(describeError(error)),
  });

  if (sessionLoading) {
    return (
      <main className="p-8">
        <p>Loading…</p>
      </main>
    );
  }

  if (!session?.authenticated) {
    return (
      <main className="p-8">
        <p role="alert">You must sign in to view this page.</p>
      </main>
    );
  }

  if (!isAdmin) {
    return (
      <main className="p-8">
        <p role="alert">You do not have permission to create projects.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-xl space-y-6 p-8">
      <h1 className="text-xl font-semibold">New project</h1>

      {submitError && (
        <p role="alert" className="text-sm text-red-700">
          {submitError}
        </p>
      )}

      <ProjectForm
        mode="create"
        register={register}
        errors={errors}
        onSubmit={handleSubmit((values) => createMutation.mutate(values))}
        isSubmitting={createMutation.isPending}
        members={membersQuery.data ?? []}
        submitLabel="Create project"
      />
    </main>
  );
}
