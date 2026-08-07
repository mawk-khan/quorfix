"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { AccessState } from "@/components/access-state";
import { AlertDialog } from "@/components/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { listMembers } from "@/lib/api/members";
import { archiveProject, getProject, restoreProject, updateProject } from "@/lib/api/projects";
import { useSession } from "@/lib/auth/session-provider";
import { usePageTitle } from "@/lib/use-page-title";
import { updateProjectSchema, type UpdateProjectFormValues } from "@/lib/validation/projects";

import { ProjectForm } from "../project-form";
import { PROJECT_STATUS_LABELS } from "../project-badges";

function describeError(error: unknown): string {
  if (error instanceof ApiError && typeof error.body === "object" && error.body !== null) {
    const body = error.body as Record<string, unknown>;
    if ("detail" in body) return String(body.detail);
    if ("lead" in body && Array.isArray(body.lead)) return String(body.lead[0]);
  }
  return "Something went wrong.";
}

function leadLabel(lead: { first_name: string; last_name: string; email: string } | null): string {
  if (!lead) return "—";
  const fullName = `${lead.first_name} ${lead.last_name}`.trim();
  return fullName || lead.email;
}

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { session, isLoading: sessionLoading } = useSession();
  const isAdmin = session?.role === "administrator";
  const queryClient = useQueryClient();

  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmingArchive, setConfirmingArchive] = useState(false);
  const archiveButtonRef = useRef<HTMLButtonElement>(null);

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", id],
    queryFn: () => getProject(id),
    enabled: !!session?.authenticated,
  });
  usePageTitle(projectQuery.data ? `${projectQuery.data.name} · Projects` : "Projects");

  const membersQuery = useQuery({
    queryKey: ["members"],
    queryFn: () => listMembers(),
    enabled: isAdmin,
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<UpdateProjectFormValues>({ resolver: zodResolver(updateProjectSchema) });

  useEffect(() => {
    if (projectQuery.data) {
      reset({
        name: projectQuery.data.name,
        description: projectQuery.data.description,
        status: projectQuery.data.status,
        lead: projectQuery.data.lead?.id ?? "",
      });
    }
  }, [projectQuery.data, reset]);

  const updateMutation = useMutation({
    mutationFn: (values: UpdateProjectFormValues) =>
      updateProject(id, {
        name: values.name,
        description: values.description || "",
        status: values.status,
        lead: values.lead || null,
      }),
    onSuccess: (project) => {
      // Only the list is invalidated (forcing a real refetch on its next
      // mount) — the detail query is updated directly below, so it isn't
      // invalidated too, which would otherwise trigger a redundant refetch
      // of the data this response already carries.
      queryClient.invalidateQueries({ queryKey: ["projects", "list"] });
      queryClient.setQueryData(["projects", "detail", id], project);
      setActionError(null);
    },
    onError: (error) => setActionError(describeError(error)),
  });

  const archiveMutation = useMutation({
    mutationFn: () => archiveProject(id),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ["projects", "list"] });
      queryClient.setQueryData(["projects", "detail", id], project);
      setConfirmingArchive(false);
      setActionError(null);
    },
    onError: (error) => setActionError(describeError(error)),
  });

  const restoreMutation = useMutation({
    mutationFn: () => restoreProject(id),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ["projects", "list"] });
      queryClient.setQueryData(["projects", "detail", id], project);
      setActionError(null);
    },
    onError: (error) => setActionError(describeError(error)),
  });

  if (sessionLoading || projectQuery.isLoading) {
    return (
      <main id="main-content" tabIndex={-1} className="mx-auto max-w-2xl space-y-6 p-8">
        <Skeleton className="h-64" />
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

  if (projectQuery.isError || !projectQuery.data) {
    const notFound = projectQuery.error instanceof ApiError && projectQuery.error.status === 404;
    return (
      <main id="main-content" tabIndex={-1} className="p-8">
        <AccessState
          heading={notFound ? "Not found" : "Something went wrong"}
          message={
            notFound
              ? "This project does not exist or you don't have access to it."
              : "Something went wrong loading this project."
          }
          action={{ href: "/projects", label: "Back to projects" }}
        />
      </main>
    );
  }

  const project = projectQuery.data;
  const isArchived = project.archived_at !== null;

  return (
    <main id="main-content" tabIndex={-1} className="mx-auto max-w-2xl space-y-6 p-8">
      <div>
        <Link
          href="/projects"
          className="inline-flex items-center gap-1 text-sm text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft aria-hidden="true" className="size-4" />
          Back to projects
        </Link>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-text-secondary">{project.key}</span>
            {isArchived && <Badge tone="amber">Archived</Badge>}
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-text-primary">{project.name}</h1>
        </div>
      </div>

      {actionError && (
        <p role="alert" className="rounded-field border border-danger/20 bg-danger-subtle p-3 text-sm text-danger">
          {actionError}
        </p>
      )}

      {!isAdmin && (
        <Card>
          <CardContent>
            <dl className="space-y-4 text-sm">
              <div>
                <dt className="font-medium text-text-primary">Description</dt>
                <dd className="mt-1 whitespace-pre-wrap text-text-secondary">{project.description || "—"}</dd>
              </div>
              <div>
                <dt className="font-medium text-text-primary">Status</dt>
                <dd className="mt-1 text-text-secondary">{PROJECT_STATUS_LABELS[project.status]}</dd>
              </div>
              <div>
                <dt className="font-medium text-text-primary">Lead</dt>
                <dd className="mt-1 text-text-secondary">{leadLabel(project.lead)}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      )}

      {isAdmin && isArchived && (
        <Card>
          <CardContent className="space-y-3">
            <p className="text-sm text-text-secondary">Restore this project before editing it.</p>
            <Button type="button" onClick={() => restoreMutation.mutate()} disabled={restoreMutation.isPending}>
              Restore project
            </Button>
          </CardContent>
        </Card>
      )}

      {isAdmin && !isArchived && (
        <Card>
          <CardContent>
            <ProjectForm
              mode="edit"
              register={register}
              errors={errors}
              onSubmit={handleSubmit((values) => updateMutation.mutate(values))}
              isSubmitting={updateMutation.isPending}
              members={membersQuery.data ?? []}
              submitLabel="Save changes"
            />
            {updateMutation.isSuccess && (
              <span role="status" className="mt-2 block text-sm text-text-secondary">
                Saved.
              </span>
            )}

            <div className="mt-6 border-t border-border pt-4">
              {!confirmingArchive ? (
                <Button ref={archiveButtonRef} type="button" variant="danger" size="sm" onClick={() => setConfirmingArchive(true)}>
                  Archive project
                </Button>
              ) : (
                <AlertDialog
                  variant="boxed"
                  title="Confirm archive project"
                  description="Archive this project?"
                  confirmLabel="Confirm"
                  onConfirm={() => archiveMutation.mutate()}
                  onCancel={() => setConfirmingArchive(false)}
                  pending={archiveMutation.isPending}
                  restoreFocusTo={archiveButtonRef}
                />
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </main>
  );
}
