"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { activityKeys, addRelationship, listBugs, removeRelationship, type CreatableRelationshipType } from "@/lib/api/bugs";
import type { Bug } from "@/lib/api/types";

const TYPE_LABELS: Record<string, string> = {
  duplicate_of: "Duplicate of",
  duplicated_by: "Duplicated by",
  blocks: "Blocks",
  blocked_by: "Blocked by",
  relates_to: "Relates to",
};

interface BugRelationshipsPanelProps {
  bug: Bug;
  onMutated: (bug: Bug) => void;
  onError: (error: unknown) => void;
}

export function BugRelationshipsPanel({ bug, onMutated, onError }: BugRelationshipsPanelProps) {
  const queryClient = useQueryClient();
  const [relatedKey, setRelatedKey] = useState("");
  const [relationshipType, setRelationshipType] = useState<CreatableRelationshipType>("relates_to");
  const [resolveError, setResolveError] = useState<string | null>(null);

  const addMutation = useMutation({
    mutationFn: async () => {
      const trimmed = relatedKey.trim();
      if (!trimmed) throw new Error("empty");
      const matches = await listBugs({ search: trimmed, archived: "all" });
      const target = matches.results.find((b) => b.key.toLowerCase() === trimmed.toLowerCase());
      if (!target) throw new Error("not-found");
      return addRelationship(bug.id, target.id, relationshipType, bug.version);
    },
    onSuccess: (updated) => {
      setRelatedKey("");
      setResolveError(null);
      queryClient.invalidateQueries({ queryKey: activityKeys.lists(bug.id) });
      onMutated(updated);
    },
    onError: (error) => {
      if (error instanceof Error && error.message === "not-found") {
        setResolveError(`No bug found with key "${relatedKey.trim()}".`);
        return;
      }
      if (error instanceof Error && error.message === "empty") return;
      onError(error);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (relationshipId: string) => removeRelationship(bug.id, relationshipId, bug.version),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: activityKeys.lists(bug.id) });
      onMutated(updated);
    },
    onError,
  });

  return (
    <div className="space-y-3">
      {bug.relationships.length === 0 && (
        <p className="text-sm text-text-secondary">No relationships yet.</p>
      )}

      <ul className="space-y-2 text-sm">
        {bug.relationships.map((rel) => (
          <li key={rel.id} className="flex items-center justify-between gap-2">
            <span className="min-w-0 text-text-primary">
              {TYPE_LABELS[rel.type] ?? rel.type}{" "}
              <Link href={`/bugs/${rel.bug.id}`} className="underline underline-offset-2 hover:text-primary">
                {rel.bug.key}
              </Link>{" "}
              — {rel.bug.title}
            </span>
            {bug.can_manage_relationships && (
              <button
                type="button"
                onClick={() => removeMutation.mutate(rel.id)}
                disabled={removeMutation.isPending}
                className="flex-none text-xs text-danger underline disabled:opacity-50"
              >
                Remove
              </button>
            )}
          </li>
        ))}
      </ul>

      {bug.can_manage_relationships && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            addMutation.mutate();
          }}
          className="flex flex-wrap items-end gap-2"
          aria-label="Add relationship"
        >
          <FormField htmlFor="relationship-bug-key" label="Bug key">
            <Input
              id="relationship-bug-key"
              value={relatedKey}
              onChange={(event) => setRelatedKey(event.target.value)}
              placeholder="e.g. BFW-2"
            />
          </FormField>
          <FormField htmlFor="relationship-type" label="Type">
            <Select
              id="relationship-type"
              value={relationshipType}
              onChange={(event) => setRelationshipType(event.target.value as CreatableRelationshipType)}
            >
              <option value="relates_to">Relates to</option>
              <option value="blocks">Blocks</option>
            </Select>
          </FormField>
          <Button type="submit" variant="secondary" size="sm" disabled={addMutation.isPending}>
            Add
          </Button>
        </form>
      )}
      {resolveError && (
        <p role="alert" className="text-sm text-danger">
          {resolveError}
        </p>
      )}
    </div>
  );
}
