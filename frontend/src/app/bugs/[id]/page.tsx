"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import {
  addTag,
  archiveBug,
  assignBug,
  getBug,
  listBugs,
  removeTag,
  restoreBug,
  transitionBug,
  unwatchBug,
  updateBug,
  watchBug,
} from "@/lib/api/bugs";
import { ApiError } from "@/lib/api/client";
import { listMembers } from "@/lib/api/members";
import type { Bug, BugStatus } from "@/lib/api/types";
import { useSession } from "@/lib/auth/session-provider";
import { addTagSchema, type AddTagFormValues, updateBugSchema, type UpdateBugFormValues } from "@/lib/validation/bugs";

import { PriorityBadge, SeverityBadge, StatusBadge } from "../bug-badges";
import { BugActivityFeed } from "./bug-activity-feed";
import { BugAttachments } from "./bug-attachments";
import { BugDiscussion } from "./bug-discussion";
import { BugRelationshipsPanel } from "./bug-relationships-panel";

const ASSIGNABLE_ROLES = new Set(["administrator", "developer", "qa"]);

function extractConflictBug(error: unknown): Bug | null {
  if (
    error instanceof ApiError &&
    error.status === 409 &&
    typeof error.body === "object" &&
    error.body !== null
  ) {
    const body = error.body as Record<string, unknown>;
    if (body.code === "bug_version_conflict" && body.bug) {
      return body.bug as Bug;
    }
  }
  return null;
}

function describeError(error: unknown): string {
  if (error instanceof ApiError && typeof error.body === "object" && error.body !== null) {
    const body = error.body as Record<string, unknown>;
    if ("detail" in body) return String(body.detail);
    for (const key of Object.keys(body)) {
      const value = body[key];
      if (Array.isArray(value) && value.length > 0) return String(value[0]);
    }
  }
  return "Something went wrong.";
}

export default function BugDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { session, isLoading: sessionLoading } = useSession();
  const queryClient = useQueryClient();

  const [actionError, setActionError] = useState<string | null>(null);
  const [conflictBug, setConflictBug] = useState<Bug | null>(null);
  const [confirmingArchive, setConfirmingArchive] = useState(false);
  const [transitionTarget, setTransitionTarget] = useState<BugStatus | "">("");
  const [duplicateOfKey, setDuplicateOfKey] = useState("");

  const bugQuery = useQuery({
    queryKey: ["bugs", "detail", id],
    queryFn: () => getBug(id),
    enabled: !!session?.authenticated,
  });

  const membersQuery = useQuery({
    queryKey: ["members"],
    queryFn: () => listMembers(),
    enabled: !!bugQuery.data?.can_assign,
  });

  const bug = bugQuery.data;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<UpdateBugFormValues>({ resolver: zodResolver(updateBugSchema) });

  const tagForm = useForm<AddTagFormValues>({ resolver: zodResolver(addTagSchema) });
  // A separate tiny form (rather than a useState synced from an effect —
  // that pattern triggers eslint's set-state-in-effect rule, since a raw
  // setState call in an effect body causes an extra cascading render;
  // react-hook-form's reset() is exempt because it's an imperative,
  // ref-based call, not a React state setter) just for the assignee select.
  const assignForm = useForm<{ assignee: string }>();

  useEffect(() => {
    if (bug) {
      reset({
        title: bug.title,
        description: bug.description,
        steps_to_reproduce: bug.steps_to_reproduce,
        expected_result: bug.expected_result,
        actual_result: bug.actual_result,
        environment: bug.environment,
        category: bug.category,
        due_date: bug.due_date ?? "",
        priority: bug.priority,
        severity: bug.severity,
      });
      assignForm.reset({ assignee: bug.assignee?.id ?? "" });
    }
  }, [bug, reset, assignForm]);

  function onMutated(updated: Bug) {
    queryClient.setQueryData(["bugs", "detail", id], updated);
    queryClient.invalidateQueries({ queryKey: ["bugs", "list"] });
    setActionError(null);
  }

  function onMutationError(error: unknown) {
    const conflict = extractConflictBug(error);
    if (conflict) {
      setConflictBug(conflict);
      return;
    }
    setActionError(describeError(error));
  }

  const updateMutation = useMutation({
    mutationFn: (values: UpdateBugFormValues) => {
      if (!bug) throw new Error("not-loaded");
      const payload: Record<string, unknown> = { version: bug.version };
      for (const field of bug.editable_fields) {
        if (field in values) {
          const value = (values as Record<string, unknown>)[field];
          // due_date is a DRF DateField — it accepts a real date string or
          // null, but not "" (an empty string fails date-format
          // validation outright, unlike the plain-text fields above where
          // "" is simply "cleared").
          payload[field] = field === "due_date" ? value || null : (value ?? "");
        }
      }
      return updateBug(bug.id, payload as never);
    },
    onSuccess: onMutated,
    onError: onMutationError,
  });

  const transitionMutation = useMutation({
    mutationFn: async () => {
      if (!bug || !transitionTarget) throw new Error("no-target");
      let duplicateOfId: string | undefined;
      if (transitionTarget === "duplicate") {
        const trimmed = duplicateOfKey.trim();
        if (!trimmed) throw new Error("duplicate-target-required");
        const matches = await listBugs({ search: trimmed, archived: "all" });
        const target = matches.results.find((b) => b.key.toLowerCase() === trimmed.toLowerCase());
        if (!target) throw new Error("duplicate-target-not-found");
        duplicateOfId = target.id;
      }
      return transitionBug(bug.id, {
        status: transitionTarget,
        version: bug.version,
        duplicate_of: duplicateOfId,
      });
    },
    onSuccess: (updated) => {
      setTransitionTarget("");
      setDuplicateOfKey("");
      onMutated(updated);
    },
    onError: (error) => {
      if (error instanceof Error && error.message === "duplicate-target-required") {
        setActionError("Enter the key of the bug this is a duplicate of.");
        return;
      }
      if (error instanceof Error && error.message === "duplicate-target-not-found") {
        setActionError(`No bug found with key "${duplicateOfKey.trim()}".`);
        return;
      }
      onMutationError(error);
    },
  });

  const assignMutation = useMutation({
    mutationFn: (values: { assignee: string }) => {
      if (!bug) throw new Error("not-loaded");
      return assignBug(bug.id, values.assignee || null, bug.version);
    },
    onSuccess: onMutated,
    onError: onMutationError,
  });

  const archiveMutation = useMutation({
    mutationFn: () => {
      if (!bug) throw new Error("not-loaded");
      return archiveBug(bug.id, bug.version);
    },
    onSuccess: (updated) => {
      setConfirmingArchive(false);
      onMutated(updated);
    },
    onError: onMutationError,
  });

  const restoreMutation = useMutation({
    mutationFn: () => {
      if (!bug) throw new Error("not-loaded");
      return restoreBug(bug.id, bug.version);
    },
    onSuccess: onMutated,
    onError: onMutationError,
  });

  const addTagMutation = useMutation({
    mutationFn: (values: AddTagFormValues) => {
      if (!bug) throw new Error("not-loaded");
      return addTag(bug.id, values.name, bug.version);
    },
    onSuccess: (updated) => {
      tagForm.reset({ name: "" });
      onMutated(updated);
    },
    onError: onMutationError,
  });

  const removeTagMutation = useMutation({
    mutationFn: (tagId: string) => {
      if (!bug) throw new Error("not-loaded");
      return removeTag(bug.id, tagId, bug.version);
    },
    onSuccess: onMutated,
    onError: onMutationError,
  });

  const watchMutation = useMutation({
    mutationFn: () => watchBug(id),
    onSuccess: onMutated,
    onError: onMutationError,
  });

  const unwatchMutation = useMutation({
    mutationFn: () => unwatchBug(id),
    onSuccess: onMutated,
    onError: onMutationError,
  });

  if (sessionLoading || bugQuery.isLoading) {
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

  if (bugQuery.isError || !bug) {
    const notFound = bugQuery.error instanceof ApiError && bugQuery.error.status === 404;
    return (
      <main className="p-8">
        <p role="alert">
          {notFound
            ? "This bug does not exist or you don't have access to it."
            : "Something went wrong loading this bug."}
        </p>
      </main>
    );
  }

  const isArchived = bug.archived_at !== null;
  const canEditContent = bug.editable_fields.length > 0;
  // Comments and attachment uploads share the same role gate on the backend
  // (apps.comments.policies.CAN_COMMENT_ROLES / apps.attachments.policies.
  // CAN_UPLOAD_ROLES — administrator, developer, qa, reporter; viewer
  // excluded). The backend re-checks this on every mutating request
  // regardless — this only controls whether the create/upload UI renders.
  const canCollaborate = session.role !== null && session.role !== "viewer";
  const eligibleAssignees = (membersQuery.data ?? []).filter((m) => ASSIGNABLE_ROLES.has(m.role));

  return (
    <main className="mx-auto max-w-3xl space-y-8 p-8">
      <div>
        <p className="font-mono text-sm text-gray-500">{bug.key}</p>
        <h1 className="text-xl font-semibold">{bug.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <StatusBadge status={bug.status} />
          <PriorityBadge priority={bug.priority} />
          <SeverityBadge severity={bug.severity} />
          {isArchived && <span className="text-sm text-amber-700">Archived</span>}
        </div>
      </div>

      {actionError && (
        <p role="alert" className="text-sm text-red-700">
          {actionError}
        </p>
      )}

      {conflictBug && (
        <div role="alert" className="space-y-2 rounded border border-amber-400 bg-amber-50 p-3 text-sm">
          <p>This bug was changed by someone else since you loaded it.</p>
          <button
            type="button"
            onClick={() => {
              queryClient.setQueryData(["bugs", "detail", id], conflictBug);
              setConflictBug(null);
            }}
            className="rounded border border-amber-600 px-3 py-1 text-amber-900"
          >
            Reload latest version
          </button>
        </div>
      )}

      {isArchived && (
        <div className="space-y-2">
          <p className="text-sm text-gray-500">This bug is archived and cannot be edited.</p>
          {bug.can_archive && (
            <button
              type="button"
              onClick={() => restoreMutation.mutate()}
              disabled={restoreMutation.isPending}
              className="rounded bg-black px-3 py-2 text-sm text-white disabled:opacity-50"
            >
              Restore bug
            </button>
          )}
        </div>
      )}

      {!isArchived && (
        <section className="space-y-4">
          <h2 className="font-medium">Details</h2>
          {canEditContent ? (
            <form
              onSubmit={handleSubmit((values) => updateMutation.mutate(values))}
              className="space-y-3"
              aria-label="Edit bug"
            >
              {bug.editable_fields.includes("title") && (
                <div>
                  <label htmlFor="edit-title" className="block text-sm font-medium">
                    Title
                  </label>
                  <input id="edit-title" className="mt-1 w-full rounded border px-3 py-2" {...register("title")} />
                  {errors.title && (
                    <p role="alert" className="mt-1 text-sm text-red-700">
                      {errors.title.message}
                    </p>
                  )}
                </div>
              )}
              {bug.editable_fields.includes("description") && (
                <div>
                  <label htmlFor="edit-description" className="block text-sm font-medium">
                    Description
                  </label>
                  <textarea
                    id="edit-description"
                    rows={3}
                    className="mt-1 w-full rounded border px-3 py-2"
                    {...register("description")}
                  />
                </div>
              )}
              {bug.editable_fields.includes("steps_to_reproduce") && (
                <div>
                  <label htmlFor="edit-steps" className="block text-sm font-medium">
                    Steps to reproduce
                  </label>
                  <textarea
                    id="edit-steps"
                    rows={3}
                    className="mt-1 w-full rounded border px-3 py-2"
                    {...register("steps_to_reproduce")}
                  />
                </div>
              )}
              {bug.editable_fields.includes("category") && (
                <div>
                  <label htmlFor="edit-category" className="block text-sm font-medium">
                    Category
                  </label>
                  <input
                    id="edit-category"
                    className="mt-1 w-full rounded border px-3 py-2"
                    {...register("category")}
                  />
                </div>
              )}
              {bug.editable_fields.includes("due_date") && (
                <div>
                  <label htmlFor="edit-due-date" className="block text-sm font-medium">
                    Due date
                  </label>
                  <input
                    id="edit-due-date"
                    type="date"
                    className="mt-1 rounded border px-3 py-2"
                    {...register("due_date")}
                  />
                </div>
              )}
              {bug.editable_fields.includes("priority") && (
                <div>
                  <label htmlFor="edit-priority" className="block text-sm font-medium">
                    Priority
                  </label>
                  <select id="edit-priority" className="mt-1 rounded border px-2 py-2" {...register("priority")}>
                    <option value="urgent">urgent</option>
                    <option value="high">high</option>
                    <option value="medium">medium</option>
                    <option value="low">low</option>
                  </select>
                </div>
              )}
              {bug.editable_fields.includes("severity") && (
                <div>
                  <label htmlFor="edit-severity" className="block text-sm font-medium">
                    Severity
                  </label>
                  <select id="edit-severity" className="mt-1 rounded border px-2 py-2" {...register("severity")}>
                    <option value="blocker">blocker</option>
                    <option value="critical">critical</option>
                    <option value="major">major</option>
                    <option value="minor">minor</option>
                    <option value="trivial">trivial</option>
                  </select>
                </div>
              )}
              <button
                type="submit"
                disabled={updateMutation.isPending}
                className="rounded bg-black px-3 py-2 text-sm text-white disabled:opacity-50"
              >
                Save changes
              </button>
            </form>
          ) : (
            <dl className="space-y-2 text-sm">
              <div>
                <dt className="font-medium">Description</dt>
                <dd className="whitespace-pre-wrap">{bug.description || "—"}</dd>
              </div>
              <div>
                <dt className="font-medium">Steps to reproduce</dt>
                <dd className="whitespace-pre-wrap">{bug.steps_to_reproduce || "—"}</dd>
              </div>
              <div>
                <dt className="font-medium">Category</dt>
                <dd>{bug.category || "—"}</dd>
              </div>
            </dl>
          )}
        </section>
      )}

      {!isArchived && bug.available_transitions.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-medium">Change status</h2>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              transitionMutation.mutate();
            }}
            className="flex flex-wrap items-end gap-2"
          >
            <div>
              <label htmlFor="transition-target" className="block text-xs font-medium">
                New status
              </label>
              <select
                id="transition-target"
                value={transitionTarget}
                onChange={(event) => setTransitionTarget(event.target.value as BugStatus | "")}
                className="mt-1 rounded border px-2 py-1 text-sm"
              >
                <option value="">Select…</option>
                {bug.available_transitions.map((status) => (
                  <option key={status} value={status}>
                    {status.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            {transitionTarget === "duplicate" && (
              <div>
                <label htmlFor="duplicate-of-key" className="block text-xs font-medium">
                  Duplicate of (bug key)
                </label>
                <input
                  id="duplicate-of-key"
                  value={duplicateOfKey}
                  onChange={(event) => setDuplicateOfKey(event.target.value)}
                  placeholder="e.g. BFW-2"
                  className="mt-1 rounded border px-2 py-1 text-sm"
                />
              </div>
            )}
            <button
              type="submit"
              disabled={!transitionTarget || transitionMutation.isPending}
              className="rounded border px-3 py-1 text-sm disabled:opacity-50"
            >
              Apply
            </button>
          </form>
        </section>
      )}

      {!isArchived && bug.can_assign && (
        <section className="space-y-2">
          <h2 className="font-medium">Assignee</h2>
          <p className="text-sm text-gray-500" data-testid="current-assignee">
            Currently assigned to:{" "}
            {bug.assignee
              ? `${bug.assignee.first_name} ${bug.assignee.last_name}`.trim() || bug.assignee.email
              : "Unassigned"}
          </p>
          <form
            onSubmit={assignForm.handleSubmit((values) => assignMutation.mutate(values))}
            className="flex items-end gap-2"
          >
            <select
              {...assignForm.register("assignee")}
              className="rounded border px-2 py-1 text-sm"
              aria-label="Assignee"
            >
              <option value="">Unassigned</option>
              {eligibleAssignees.map((member) => (
                <option key={member.id} value={member.user.id}>
                  {member.user.first_name} {member.user.last_name} ({member.user.email})
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={assignMutation.isPending}
              className="rounded border px-3 py-1 text-sm disabled:opacity-50"
            >
              Update assignee
            </button>
          </form>
        </section>
      )}

      <section className="space-y-2">
        <h2 className="font-medium">Tags</h2>
        <ul className="flex flex-wrap gap-2">
          {bug.tags.map((tag) => (
            <li key={tag.id} className="flex items-center gap-1 rounded border px-2 py-1 text-xs">
              {tag.name}
              {canEditContent && !isArchived && (
                <button
                  type="button"
                  onClick={() => removeTagMutation.mutate(tag.id)}
                  disabled={removeTagMutation.isPending}
                  className="text-red-700"
                  aria-label={`Remove tag ${tag.name}`}
                >
                  ×
                </button>
              )}
            </li>
          ))}
          {bug.tags.length === 0 && <li className="text-sm text-gray-500">No tags.</li>}
        </ul>
        {canEditContent && !isArchived && (
          <form
            onSubmit={tagForm.handleSubmit((values) => addTagMutation.mutate(values))}
            className="flex items-end gap-2"
            aria-label="Add tag"
          >
            <div>
              <label htmlFor="new-tag-name" className="block text-xs font-medium">
                New tag
              </label>
              <input
                id="new-tag-name"
                className="mt-1 rounded border px-2 py-1 text-sm"
                {...tagForm.register("name")}
              />
            </div>
            <button
              type="submit"
              disabled={addTagMutation.isPending}
              className="rounded border px-3 py-1 text-sm disabled:opacity-50"
            >
              Add
            </button>
          </form>
        )}
      </section>

      <section className="flex items-center gap-3">
        {bug.is_watching ? (
          <button
            type="button"
            onClick={() => unwatchMutation.mutate()}
            disabled={unwatchMutation.isPending}
            className="rounded border px-3 py-2 text-sm disabled:opacity-50"
          >
            Unwatch
          </button>
        ) : (
          <button
            type="button"
            onClick={() => watchMutation.mutate()}
            disabled={watchMutation.isPending}
            className="rounded border px-3 py-2 text-sm disabled:opacity-50"
          >
            Watch
          </button>
        )}
        <span className="text-sm text-gray-500">
          {bug.watcher_count} watcher{bug.watcher_count === 1 ? "" : "s"}
        </span>
      </section>

      {!isArchived && <BugRelationshipsPanel bug={bug} onMutated={onMutated} onError={onMutationError} />}

      {!isArchived && bug.can_archive && (
        <section className="border-t pt-4">
          {!confirmingArchive ? (
            <button
              type="button"
              onClick={() => setConfirmingArchive(true)}
              className="text-sm text-red-700 underline"
            >
              Archive bug
            </button>
          ) : (
            <div className="flex items-center gap-3 text-sm">
              <span>Archive this bug?</span>
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
        </section>
      )}

      <section className="space-y-2 border-t pt-4">
        <h2 className="font-medium">Attachments</h2>
        <BugAttachments bugId={bug.id} isArchived={isArchived} canUpload={canCollaborate} />
      </section>

      <section className="space-y-2 border-t pt-4">
        <h2 className="font-medium">Discussion</h2>
        <BugDiscussion bugId={bug.id} isArchived={isArchived} canComment={canCollaborate} />
      </section>

      <section className="space-y-2 border-t pt-4">
        <h2 className="font-medium">Activity</h2>
        <BugActivityFeed bugId={bug.id} />
      </section>
    </main>
  );
}
