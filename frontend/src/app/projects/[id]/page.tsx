"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "@/lib/api/client";
import { listMembers } from "@/lib/api/members";
import { archiveProject, getProject, restoreProject, updateProject } from "@/lib/api/projects";
import { useSession } from "@/lib/auth/session-provider";
import { updateProjectSchema, type UpdateProjectFormValues } from "@/lib/validation/projects";

import { ProjectForm } from "../project-form";

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

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", id],
    queryFn: () => getProject(id),
    enabled: !!session?.authenticated,
  });

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

  if (projectQuery.isError || !projectQuery.data) {
    const notFound = projectQuery.error instanceof ApiError && projectQuery.error.status === 404;
    return (
      <main className="p-8">
        <p role="alert">
          {notFound
            ? "This project does not exist or you don't have access to it."
            : "Something went wrong loading this project."}
        </p>
      </main>
    );
  }

  const project = projectQuery.data;
  const isArchived = project.archived_at !== null;

  return (
    <main className="mx-auto max-w-xl space-y-6 p-8">
      <div>
        <p className="font-mono text-sm text-gray-500">{project.key}</p>
        <h1 className="text-xl font-semibold">{project.name}</h1>
        {isArchived && <p className="mt-1 text-sm text-amber-700">Archived</p>}
      </div>

      {actionError && (
        <p role="alert" className="text-sm text-red-700">
          {actionError}
        </p>
      )}

      {!isAdmin && (
        <dl className="space-y-2 text-sm">
          <div>
            <dt className="font-medium">Description</dt>
            <dd>{project.description || "—"}</dd>
          </div>
          <div>
            <dt className="font-medium">Status</dt>
            <dd>{project.status.replace("_", " ")}</dd>
          </div>
          <div>
            <dt className="font-medium">Lead</dt>
            <dd>{leadLabel(project.lead)}</dd>
          </div>
        </dl>
      )}

      {isAdmin && isArchived && (
        <div className="space-y-3">
          <p className="text-sm text-gray-500">Restore this project before editing it.</p>
          <button
            type="button"
            onClick={() => restoreMutation.mutate()}
            disabled={restoreMutation.isPending}
            className="rounded bg-black px-3 py-2 text-sm text-white disabled:opacity-50"
          >
            Restore project
          </button>
        </div>
      )}

      {isAdmin && !isArchived && (
        <>
          <ProjectForm
            mode="edit"
            register={register}
            errors={errors}
            onSubmit={handleSubmit((values) => updateMutation.mutate(values))}
            isSubmitting={updateMutation.isPending}
            members={membersQuery.data ?? []}
            submitLabel="Save changes"
          />

          <div className="border-t pt-4">
            {!confirmingArchive ? (
              <button
                type="button"
                onClick={() => setConfirmingArchive(true)}
                className="text-sm text-red-700 underline"
              >
                Archive project
              </button>
            ) : (
              <div className="flex items-center gap-3 text-sm">
                <span>Archive this project?</span>
                <button
                  type="button"
                  onClick={() => archiveMutation.mutate()}
                  disabled={archiveMutation.isPending}
                  className="text-red-700 underline"
                >
                  Confirm
                </button>
                <button type="button" onClick={() => setConfirmingArchive(false)} className="underline">
                  Cancel
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </main>
  );
}
