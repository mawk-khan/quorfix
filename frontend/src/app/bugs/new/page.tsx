"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { AccessState } from "@/components/access-state";
import { createBug } from "@/lib/api/bugs";
import { ApiError } from "@/lib/api/client";
import { listProjects } from "@/lib/api/projects";
import { useSession } from "@/lib/auth/session-provider";
import { errorProps } from "@/lib/forms/error-props";
import { BUG_PRIORITIES, BUG_SEVERITIES, createBugSchema, type CreateBugFormValues } from "@/lib/validation/bugs";

function describeError(error: unknown): string {
  if (error instanceof ApiError && typeof error.body === "object" && error.body !== null) {
    const body = error.body as Record<string, unknown>;
    if ("detail" in body) return String(body.detail);
    if ("project" in body && Array.isArray(body.project)) return String(body.project[0]);
    if ("title" in body && Array.isArray(body.title)) return String(body.title[0]);
  }
  return "Something went wrong creating the bug.";
}

export default function NewBugPage() {
  const { session, isLoading: sessionLoading } = useSession();
  const canCreate = session?.role !== null && session?.role !== "viewer";
  const router = useRouter();
  const queryClient = useQueryClient();
  const [submitError, setSubmitError] = useState<string | null>(null);

  const projectsQuery = useQuery({
    queryKey: ["projects", "list", "for-new-bug"],
    queryFn: () => listProjects({ archived: "false" }),
    enabled: !!session?.authenticated,
  });

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CreateBugFormValues>({
    resolver: zodResolver(createBugSchema),
    defaultValues: { priority: "medium", severity: "major" },
  });

  const createMutation = useMutation({
    mutationFn: (values: CreateBugFormValues) =>
      createBug({
        project: values.project,
        title: values.title,
        description: values.description || "",
        steps_to_reproduce: values.steps_to_reproduce || "",
        expected_result: values.expected_result || "",
        actual_result: values.actual_result || "",
        environment: values.environment || "",
        category: values.category || "",
        priority: values.priority,
        severity: values.severity,
        due_date: values.due_date || null,
      }),
    onSuccess: (bug) => {
      queryClient.invalidateQueries({ queryKey: ["bugs", "list"] });
      router.push(`/bugs/${bug.id}`);
    },
    onError: (error) => setSubmitError(describeError(error)),
  });

  if (sessionLoading) {
    return (
      <main id="main-content" tabIndex={-1} className="p-8">
        <p>Loading…</p>
      </main>
    );
  }

  if (!session?.authenticated) {
    return (
      <main id="main-content" tabIndex={-1} className="p-8">
        <AccessState
          heading="Sign in required"
          message="You must sign in to view this page."
          action={{ href: "/sign-in", label: "Go to sign in" }}
        />
      </main>
    );
  }

  if (!canCreate) {
    return (
      <main id="main-content" tabIndex={-1} className="p-8">
        <AccessState heading="Access restricted" message="You do not have permission to create bugs." />
      </main>
    );
  }

  const projects = projectsQuery.data?.results ?? [];

  return (
    <main id="main-content" tabIndex={-1} className="mx-auto max-w-xl space-y-6 p-8">
      <h1 className="text-xl font-semibold">New bug</h1>

      {submitError && (
        <p role="alert" className="text-sm text-red-700">
          {submitError}
        </p>
      )}

      <form
        onSubmit={handleSubmit((values) => createMutation.mutate(values))}
        className="space-y-4"
        aria-label="Create bug"
      >
        <div>
          <label htmlFor="bug-project" className="block text-sm font-medium">
            Project
          </label>
          <select
            id="bug-project"
            className="mt-1 w-full rounded border px-2 py-2"
            {...errorProps("bug-project", errors.project)}
            {...register("project")}
          >
            <option value="">Select a project…</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.key} — {project.name}
              </option>
            ))}
          </select>
          {errors.project && (
            <p id="bug-project-error" role="alert" className="mt-1 text-sm text-red-700">
              {errors.project.message}
            </p>
          )}
        </div>

        <div>
          <label htmlFor="bug-title" className="block text-sm font-medium">
            Title
          </label>
          <input
            id="bug-title"
            className="mt-1 w-full rounded border px-3 py-2"
            {...errorProps("bug-title", errors.title)}
            {...register("title")}
          />
          {errors.title && (
            <p id="bug-title-error" role="alert" className="mt-1 text-sm text-red-700">
              {errors.title.message}
            </p>
          )}
        </div>

        <div>
          <label htmlFor="bug-description" className="block text-sm font-medium">
            Description
          </label>
          <textarea
            id="bug-description"
            rows={3}
            className="mt-1 w-full rounded border px-3 py-2"
            {...register("description")}
          />
        </div>

        <div>
          <label htmlFor="bug-steps" className="block text-sm font-medium">
            Steps to reproduce
          </label>
          <textarea
            id="bug-steps"
            rows={3}
            className="mt-1 w-full rounded border px-3 py-2"
            {...register("steps_to_reproduce")}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="bug-expected" className="block text-sm font-medium">
              Expected result
            </label>
            <textarea
              id="bug-expected"
              rows={2}
              className="mt-1 w-full rounded border px-3 py-2"
              {...register("expected_result")}
            />
          </div>
          <div>
            <label htmlFor="bug-actual" className="block text-sm font-medium">
              Actual result
            </label>
            <textarea
              id="bug-actual"
              rows={2}
              className="mt-1 w-full rounded border px-3 py-2"
              {...register("actual_result")}
            />
          </div>
        </div>

        <div>
          <label htmlFor="bug-environment" className="block text-sm font-medium">
            Environment
          </label>
          <textarea
            id="bug-environment"
            rows={2}
            className="mt-1 w-full rounded border px-3 py-2"
            placeholder="Browser, OS, app version…"
            {...register("environment")}
          />
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label htmlFor="bug-category" className="block text-sm font-medium">
              Category
            </label>
            <input
              id="bug-category"
              className="mt-1 w-full rounded border px-3 py-2"
              {...register("category")}
            />
          </div>
          <div>
            <label htmlFor="bug-priority" className="block text-sm font-medium">
              Priority
            </label>
            <select
              id="bug-priority"
              className="mt-1 w-full rounded border px-2 py-2"
              {...register("priority")}
            >
              {BUG_PRIORITIES.map((priority) => (
                <option key={priority} value={priority}>
                  {priority}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="bug-severity" className="block text-sm font-medium">
              Severity
            </label>
            <select
              id="bug-severity"
              className="mt-1 w-full rounded border px-2 py-2"
              {...register("severity")}
            >
              {BUG_SEVERITIES.map((severity) => (
                <option key={severity} value={severity}>
                  {severity}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label htmlFor="bug-due-date" className="block text-sm font-medium">
            Due date
          </label>
          <input
            id="bug-due-date"
            type="date"
            className="mt-1 rounded border px-3 py-2"
            {...register("due_date")}
          />
        </div>

        <button
          type="submit"
          disabled={createMutation.isPending}
          className="rounded bg-black px-3 py-2 text-white disabled:opacity-50"
        >
          Create bug
        </button>
      </form>
    </main>
  );
}
