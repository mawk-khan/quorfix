"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Eye, EyeOff, Pencil } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";

import { AccessState } from "@/components/access-state";
import { AlertDialog } from "@/components/alert-dialog";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
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
import { formatDateTime, formatStatusLabel } from "@/lib/dashboard/format";
import { errorProps } from "@/lib/forms/error-props";
import { usePageTitle } from "@/lib/use-page-title";
import { addTagSchema, type AddTagFormValues, updateBugSchema, type UpdateBugFormValues } from "@/lib/validation/bugs";
import { BUG_PRIORITIES, BUG_SEVERITIES } from "@/lib/validation/bugs";

import { PRIORITY_LABELS, SEVERITY_LABELS, PriorityBadge, SeverityBadge, StatusBadge } from "../bug-badges";
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

function userLabel(user: { first_name: string; last_name: string; email: string }): string {
  const fullName = `${user.first_name} ${user.last_name}`.trim();
  return fullName || user.email;
}

export default function BugDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { session, isLoading: sessionLoading } = useSession();
  const queryClient = useQueryClient();

  const [actionError, setActionError] = useState<string | null>(null);
  const [conflictBug, setConflictBug] = useState<Bug | null>(null);
  const [confirmingArchive, setConfirmingArchive] = useState(false);
  const archiveButtonRef = useRef<HTMLButtonElement>(null);
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
  usePageTitle(bug ? `${bug.key} · Bugs` : "Bugs");

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
      <main id="main-content" tabIndex={-1} className="mx-auto max-w-6xl space-y-6 p-8">
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

  if (bugQuery.isError || !bug) {
    const notFound = bugQuery.error instanceof ApiError && bugQuery.error.status === 404;
    return (
      <main id="main-content" tabIndex={-1} className="p-8">
        <AccessState
          heading={notFound ? "Not found" : "Something went wrong"}
          message={
            notFound
              ? "This bug does not exist or you don't have access to it."
              : "Something went wrong loading this bug."
          }
          action={{ href: "/bugs", label: "Back to bugs" }}
        />
      </main>
    );
  }

  const isArchived = bug.archived_at !== null;
  const canEditContent = bug.editable_fields.length > 0 && !isArchived;
  // Comments and attachment uploads share the same role gate on the backend
  // (apps.comments.policies.CAN_COMMENT_ROLES / apps.attachments.policies.
  // CAN_UPLOAD_ROLES — administrator, developer, qa, reporter; viewer
  // excluded). The backend re-checks this on every mutating request
  // regardless — this only controls whether the create/upload UI renders.
  const canCollaborate = session.role !== null && session.role !== "viewer";
  const eligibleAssignees = (membersQuery.data ?? []).filter((m) => ASSIGNABLE_ROLES.has(m.role));

  function jumpToEdit() {
    const field = document.getElementById("edit-title");
    field?.focus();
    field?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  return (
    <main id="main-content" tabIndex={-1} className="mx-auto max-w-6xl space-y-6 p-8">
      <div>
        <Link
          href="/bugs"
          className="inline-flex items-center gap-1 text-sm text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft aria-hidden="true" className="size-4" />
          Back to bugs
        </Link>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-text-secondary">{bug.key}</span>
            <StatusBadge status={bug.status} />
            <PriorityBadge priority={bug.priority} />
            <SeverityBadge severity={bug.severity} />
            {isArchived && <Badge tone="amber">Archived</Badge>}
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-text-primary">{bug.title}</h1>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-text-secondary">
            {bug.watcher_count} watcher{bug.watcher_count === 1 ? "" : "s"}
          </span>
          {bug.is_watching ? (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              icon={<EyeOff aria-hidden="true" className="size-4" />}
              onClick={() => unwatchMutation.mutate()}
              disabled={unwatchMutation.isPending}
            >
              Unwatch
            </Button>
          ) : (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              icon={<Eye aria-hidden="true" className="size-4" />}
              onClick={() => watchMutation.mutate()}
              disabled={watchMutation.isPending}
            >
              Watch
            </Button>
          )}
          {canEditContent && (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              icon={<Pencil aria-hidden="true" className="size-4" />}
              onClick={jumpToEdit}
            >
              Edit
            </Button>
          )}
          {bug.can_archive &&
            (isArchived ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => restoreMutation.mutate()}
                disabled={restoreMutation.isPending}
              >
                Restore bug
              </Button>
            ) : (
              <Button
                ref={archiveButtonRef}
                type="button"
                variant="danger"
                size="sm"
                onClick={() => setConfirmingArchive(true)}
              >
                Archive bug
              </Button>
            ))}
        </div>
      </div>

      {actionError && (
        <p role="alert" className="rounded-field border border-danger/20 bg-danger-subtle p-3 text-sm text-danger">
          {actionError}
        </p>
      )}

      {conflictBug && (
        <div
          role="alert"
          className="space-y-2 rounded-field border border-warning/30 bg-warning-subtle p-3 text-sm text-warning"
        >
          <p>This bug was changed by someone else since you loaded it.</p>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => {
              queryClient.setQueryData(["bugs", "detail", id], conflictBug);
              setConflictBug(null);
            }}
          >
            Reload latest version
          </Button>
        </div>
      )}

      {confirmingArchive && (
        <AlertDialog
          variant="boxed"
          title="Confirm archive bug"
          description="Archive this bug?"
          confirmLabel="Confirm"
          onConfirm={() => archiveMutation.mutate()}
          onCancel={() => setConfirmingArchive(false)}
          pending={archiveMutation.isPending}
          restoreFocusTo={archiveButtonRef}
        />
      )}

      {isArchived && (
        <p className="text-sm text-text-secondary">This bug is archived and cannot be edited.</p>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardHeader title="Details" />
            <CardContent>
              {canEditContent ? (
                <form
                  onSubmit={handleSubmit((values) => updateMutation.mutate(values))}
                  className="space-y-4"
                  aria-label="Edit bug"
                >
                  {bug.editable_fields.includes("title") && (
                    <FormField htmlFor="edit-title" label="Title" error={errors.title}>
                      <Input id="edit-title" {...errorProps("edit-title", errors.title)} {...register("title")} />
                    </FormField>
                  )}
                  {bug.editable_fields.includes("description") && (
                    <FormField htmlFor="edit-description" label="Description" error={errors.description}>
                      <Textarea id="edit-description" rows={3} {...register("description")} />
                    </FormField>
                  )}
                  {bug.editable_fields.includes("steps_to_reproduce") && (
                    <FormField htmlFor="edit-steps" label="Steps to reproduce" error={errors.steps_to_reproduce}>
                      <Textarea id="edit-steps" rows={3} {...register("steps_to_reproduce")} />
                    </FormField>
                  )}
                  {(bug.editable_fields.includes("expected_result") ||
                    bug.editable_fields.includes("actual_result")) && (
                    <div className="grid gap-4 sm:grid-cols-2">
                      {bug.editable_fields.includes("expected_result") && (
                        <FormField htmlFor="edit-expected" label="Expected result" error={errors.expected_result}>
                          <Textarea id="edit-expected" rows={2} {...register("expected_result")} />
                        </FormField>
                      )}
                      {bug.editable_fields.includes("actual_result") && (
                        <FormField htmlFor="edit-actual" label="Actual result" error={errors.actual_result}>
                          <Textarea id="edit-actual" rows={2} {...register("actual_result")} />
                        </FormField>
                      )}
                    </div>
                  )}
                  {bug.editable_fields.includes("environment") && (
                    <FormField htmlFor="edit-environment" label="Environment" error={errors.environment}>
                      <Textarea id="edit-environment" rows={2} {...register("environment")} />
                    </FormField>
                  )}
                  {(bug.editable_fields.includes("category") || bug.editable_fields.includes("due_date")) && (
                    <div className="grid gap-4 sm:grid-cols-2">
                      {bug.editable_fields.includes("category") && (
                        <FormField htmlFor="edit-category" label="Category" error={errors.category}>
                          <Input id="edit-category" {...register("category")} />
                        </FormField>
                      )}
                      {bug.editable_fields.includes("due_date") && (
                        <FormField htmlFor="edit-due-date" label="Due date" error={errors.due_date}>
                          <Input id="edit-due-date" type="date" {...register("due_date")} />
                        </FormField>
                      )}
                    </div>
                  )}
                  {(bug.editable_fields.includes("priority") || bug.editable_fields.includes("severity")) && (
                    <div className="grid gap-4 sm:grid-cols-2">
                      {bug.editable_fields.includes("priority") && (
                        <FormField htmlFor="edit-priority" label="Priority" error={errors.priority}>
                          <Select id="edit-priority" {...register("priority")}>
                            {BUG_PRIORITIES.map((priority) => (
                              <option key={priority} value={priority}>
                                {PRIORITY_LABELS[priority]}
                              </option>
                            ))}
                          </Select>
                        </FormField>
                      )}
                      {bug.editable_fields.includes("severity") && (
                        <FormField htmlFor="edit-severity" label="Severity" error={errors.severity}>
                          <Select id="edit-severity" {...register("severity")}>
                            {BUG_SEVERITIES.map((severity) => (
                              <option key={severity} value={severity}>
                                {SEVERITY_LABELS[severity]}
                              </option>
                            ))}
                          </Select>
                        </FormField>
                      )}
                    </div>
                  )}
                  <div className="flex items-center gap-3 border-t border-border pt-4">
                    <Button type="submit" loading={updateMutation.isPending}>
                      Save changes
                    </Button>
                    {updateMutation.isSuccess && (
                      <span role="status" className="text-sm text-text-secondary">
                        Saved.
                      </span>
                    )}
                  </div>
                </form>
              ) : (
                <dl className="space-y-4 text-sm">
                  <div>
                    <dt className="font-medium text-text-primary">Description</dt>
                    <dd className="mt-1 whitespace-pre-wrap text-text-secondary">{bug.description || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-text-primary">Steps to reproduce</dt>
                    <dd className="mt-1 whitespace-pre-wrap text-text-secondary">
                      {bug.steps_to_reproduce || "—"}
                    </dd>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <dt className="font-medium text-text-primary">Expected result</dt>
                      <dd className="mt-1 whitespace-pre-wrap text-text-secondary">
                        {bug.expected_result || "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="font-medium text-text-primary">Actual result</dt>
                      <dd className="mt-1 whitespace-pre-wrap text-text-secondary">{bug.actual_result || "—"}</dd>
                    </div>
                  </div>
                  <div>
                    <dt className="font-medium text-text-primary">Environment</dt>
                    <dd className="mt-1 whitespace-pre-wrap text-text-secondary">{bug.environment || "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-text-primary">Category</dt>
                    <dd className="mt-1 text-text-secondary">{bug.category || "—"}</dd>
                  </div>
                </dl>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader title="Attachments" />
            <CardContent>
              <BugAttachments bugId={bug.id} isArchived={isArchived} canUpload={canCollaborate} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader title="Discussion" />
            <CardContent>
              <BugDiscussion bugId={bug.id} isArchived={isArchived} canComment={canCollaborate} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Status" />
            <CardContent className="space-y-4">
              {!isArchived && bug.available_transitions.length > 0 && (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    transitionMutation.mutate();
                  }}
                  className="space-y-2 border-b border-border pb-4"
                >
                  <FormField htmlFor="transition-target" label="Change status">
                    <Select
                      id="transition-target"
                      value={transitionTarget}
                      onChange={(event) => setTransitionTarget(event.target.value as BugStatus | "")}
                    >
                      <option value="">Select…</option>
                      {bug.available_transitions.map((status) => (
                        <option key={status} value={status}>
                          {formatStatusLabel(status)}
                        </option>
                      ))}
                    </Select>
                  </FormField>
                  {transitionTarget === "duplicate" && (
                    <FormField htmlFor="duplicate-of-key" label="Duplicate of (bug key)">
                      <Input
                        id="duplicate-of-key"
                        value={duplicateOfKey}
                        onChange={(event) => setDuplicateOfKey(event.target.value)}
                        placeholder="e.g. BFW-2"
                      />
                    </FormField>
                  )}
                  <Button
                    type="submit"
                    variant="secondary"
                    size="sm"
                    disabled={!transitionTarget || transitionMutation.isPending}
                  >
                    Apply
                  </Button>
                </form>
              )}

              <div>
                <p className="text-xs font-medium text-text-secondary">Assignee</p>
                {bug.can_assign ? (
                  <form
                    onSubmit={assignForm.handleSubmit((values) => assignMutation.mutate(values))}
                    className="mt-1.5 space-y-2"
                  >
                    <Select {...assignForm.register("assignee")} aria-label="Assignee">
                      <option value="">Unassigned</option>
                      {eligibleAssignees.map((member) => (
                        <option key={member.id} value={member.user.id}>
                          {userLabel(member.user)} ({member.user.email})
                        </option>
                      ))}
                    </Select>
                    <Button type="submit" variant="secondary" size="sm" disabled={assignMutation.isPending}>
                      Update assignee
                    </Button>
                  </form>
                ) : (
                  <div className="mt-1.5 flex items-center gap-2">
                    {bug.assignee ? (
                      <>
                        <Avatar user={bug.assignee} size="sm" />
                        <span className="text-sm text-text-primary">{userLabel(bug.assignee)}</span>
                      </>
                    ) : (
                      <span className="text-sm text-text-secondary">Unassigned</span>
                    )}
                  </div>
                )}
              </div>

              <div>
                <p className="text-xs font-medium text-text-secondary">Reporter</p>
                <div className="mt-1.5 flex items-center gap-2">
                  <Avatar user={bug.reporter} size="sm" />
                  <span className="text-sm text-text-primary">{userLabel(bug.reporter)}</span>
                </div>
              </div>

              <div>
                <p className="text-xs font-medium text-text-secondary">Created</p>
                <p className="mt-1 text-sm text-text-primary">{formatDateTime(bug.created_at)}</p>
              </div>

              <div>
                <p className="text-xs font-medium text-text-secondary">Last updated</p>
                <p className="mt-1 text-sm text-text-primary">{formatDateTime(bug.updated_at)}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader title="Project" />
            <CardContent>
              <Link
                href={`/projects/${bug.project.id}`}
                className="flex items-center gap-2.5 text-sm font-medium text-text-primary hover:text-primary"
              >
                <span className="flex size-8 flex-none items-center justify-center rounded-field bg-primary text-xs font-semibold text-white">
                  {bug.project.key.slice(0, 2)}
                </span>
                {bug.project.name}
              </Link>
            </CardContent>
          </Card>

          <Card>
            <CardHeader title="Tags" />
            <CardContent className="space-y-3">
              <ul className="flex flex-wrap gap-1.5">
                {bug.tags.map((tag) => (
                  <li key={tag.id}>
                    <Badge tone="neutral" className="gap-1">
                      {tag.name}
                      {canEditContent && (
                        <button
                          type="button"
                          onClick={() => removeTagMutation.mutate(tag.id)}
                          disabled={removeTagMutation.isPending}
                          className="text-text-secondary hover:text-danger"
                          aria-label={`Remove tag ${tag.name}`}
                        >
                          ×
                        </button>
                      )}
                    </Badge>
                  </li>
                ))}
                {bug.tags.length === 0 && <li className="text-sm text-text-secondary">No tags.</li>}
              </ul>
              {canEditContent && (
                <form
                  onSubmit={tagForm.handleSubmit((values) => addTagMutation.mutate(values))}
                  className="flex items-end gap-2"
                  aria-label="Add tag"
                >
                  <FormField htmlFor="new-tag-name" label="New tag" error={tagForm.formState.errors.name}>
                    <Input
                      id="new-tag-name"
                      {...errorProps("new-tag-name", tagForm.formState.errors.name)}
                      {...tagForm.register("name")}
                    />
                  </FormField>
                  <Button type="submit" variant="secondary" size="sm" disabled={addTagMutation.isPending}>
                    Add
                  </Button>
                </form>
              )}
            </CardContent>
          </Card>

          {!isArchived && (
            <Card>
              <CardHeader title="Relationships" />
              <CardContent>
                <BugRelationshipsPanel bug={bug} onMutated={onMutated} onError={onMutationError} />
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader title="Activity" />
            <CardContent>
              <BugActivityFeed bugId={bug.id} />
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}
