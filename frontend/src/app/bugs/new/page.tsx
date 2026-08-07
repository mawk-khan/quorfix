"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { AccessState } from "@/components/access-state";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Input, Textarea } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { createBug } from "@/lib/api/bugs";
import { ApiError } from "@/lib/api/client";
import { listProjects } from "@/lib/api/projects";
import { useSession } from "@/lib/auth/session-provider";
import { errorProps } from "@/lib/forms/error-props";
import { usePageTitle } from "@/lib/use-page-title";
import { BUG_PRIORITIES, BUG_SEVERITIES, createBugSchema, type CreateBugFormValues } from "@/lib/validation/bugs";

import { PRIORITY_LABELS, SEVERITY_LABELS } from "../bug-badges";

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
  usePageTitle("New bug");
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
    <main id="main-content" tabIndex={-1} className="mx-auto max-w-2xl space-y-6 p-8">
      <PageHeader
        title="New bug"
        description="Report a new bug with detailed information for proper tracking."
      />

      {submitError && (
        <p role="alert" className="rounded-field border border-danger/20 bg-danger-subtle p-3 text-sm text-danger">
          {submitError}
        </p>
      )}

      <Card>
        <CardContent>
          <form
            onSubmit={handleSubmit((values) => createMutation.mutate(values))}
            className="space-y-4"
            aria-label="Create bug"
          >
            <FormField htmlFor="bug-project" label="Project" required error={errors.project}>
              <Select
                id="bug-project"
                {...errorProps("bug-project", errors.project)}
                {...register("project")}
              >
                <option value="">Select a project…</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.key} — {project.name}
                  </option>
                ))}
              </Select>
            </FormField>

            <FormField htmlFor="bug-title" label="Title" required error={errors.title}>
              <Input
                id="bug-title"
                {...errorProps("bug-title", errors.title)}
                {...register("title")}
              />
            </FormField>

            <FormField htmlFor="bug-description" label="Description" error={errors.description}>
              <Textarea id="bug-description" rows={3} {...register("description")} />
            </FormField>

            <FormField htmlFor="bug-steps" label="Steps to reproduce" error={errors.steps_to_reproduce}>
              <Textarea id="bug-steps" rows={3} {...register("steps_to_reproduce")} />
            </FormField>

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField htmlFor="bug-expected" label="Expected result" error={errors.expected_result}>
                <Textarea id="bug-expected" rows={2} {...register("expected_result")} />
              </FormField>
              <FormField htmlFor="bug-actual" label="Actual result" error={errors.actual_result}>
                <Textarea id="bug-actual" rows={2} {...register("actual_result")} />
              </FormField>
            </div>

            <FormField htmlFor="bug-environment" label="Environment" error={errors.environment}>
              <Textarea
                id="bug-environment"
                rows={2}
                placeholder="Browser, OS, app version…"
                {...register("environment")}
              />
            </FormField>

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField htmlFor="bug-category" label="Category" error={errors.category}>
                <Input id="bug-category" {...register("category")} />
              </FormField>
              <FormField htmlFor="bug-due-date" label="Due date" error={errors.due_date}>
                <Input id="bug-due-date" type="date" {...register("due_date")} />
              </FormField>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField htmlFor="bug-priority" label="Priority" error={errors.priority}>
                <Select id="bug-priority" {...register("priority")}>
                  {BUG_PRIORITIES.map((priority) => (
                    <option key={priority} value={priority}>
                      {PRIORITY_LABELS[priority]}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField htmlFor="bug-severity" label="Severity" error={errors.severity}>
                <Select id="bug-severity" {...register("severity")}>
                  {BUG_SEVERITIES.map((severity) => (
                    <option key={severity} value={severity}>
                      {SEVERITY_LABELS[severity]}
                    </option>
                  ))}
                </Select>
              </FormField>
            </div>

            <div className="flex items-center justify-end gap-3 border-t border-border pt-4">
              <Link href="/bugs" className={buttonVariants("secondary", "md")}>
                Cancel
              </Link>
              <Button type="submit" loading={createMutation.isPending}>
                Create bug
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
