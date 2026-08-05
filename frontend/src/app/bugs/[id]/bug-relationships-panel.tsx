"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

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
      <h2 className="font-medium">Relationships</h2>

      {bug.relationships.length === 0 && <p className="text-sm text-gray-500">No relationships yet.</p>}

      <ul className="space-y-1 text-sm">
        {bug.relationships.map((rel) => (
          <li key={rel.id} className="flex items-center justify-between">
            <span>
              {TYPE_LABELS[rel.type] ?? rel.type}{" "}
              <Link href={`/bugs/${rel.bug.id}`} className="underline">
                {rel.bug.key}
              </Link>{" "}
              — {rel.bug.title}
            </span>
            {bug.can_manage_relationships && (
              <button
                type="button"
                onClick={() => removeMutation.mutate(rel.id)}
                disabled={removeMutation.isPending}
                className="text-xs text-red-700 underline disabled:opacity-50"
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
          <div>
            <label htmlFor="relationship-bug-key" className="block text-xs font-medium">
              Bug key
            </label>
            <input
              id="relationship-bug-key"
              value={relatedKey}
              onChange={(event) => setRelatedKey(event.target.value)}
              placeholder="e.g. BFW-2"
              className="mt-1 rounded border px-2 py-1 text-sm"
            />
          </div>
          <div>
            <label htmlFor="relationship-type" className="block text-xs font-medium">
              Type
            </label>
            <select
              id="relationship-type"
              value={relationshipType}
              onChange={(event) => setRelationshipType(event.target.value as CreatableRelationshipType)}
              className="mt-1 rounded border px-2 py-1 text-sm"
            >
              <option value="relates_to">Relates to</option>
              <option value="blocks">Blocks</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={addMutation.isPending}
            className="rounded border px-3 py-1 text-sm disabled:opacity-50"
          >
            Add
          </button>
        </form>
      )}
      {resolveError && (
        <p role="alert" className="text-sm text-red-700">
          {resolveError}
        </p>
      )}
    </div>
  );
}
