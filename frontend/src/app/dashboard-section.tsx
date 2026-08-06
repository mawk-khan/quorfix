"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api/client";

function describeError(error: unknown): string {
  if (
    error instanceof ApiError &&
    typeof error.body === "object" &&
    error.body !== null &&
    "detail" in error.body
  ) {
    return String((error.body as { detail: unknown }).detail);
  }
  return "Something went wrong loading this section.";
}

interface DashboardSectionProps<T> {
  title: string;
  query: Pick<UseQueryResult<T>, "data" | "isLoading" | "isError" | "error" | "refetch">;
  isEmpty?: (data: T) => boolean;
  emptyMessage?: string;
  children: (data: T) => ReactNode;
}

// Shared loading/error/retry/empty chrome for every dashboard section — one
// section failing (isError) never hides the others, since each is an
// independent query rendered independently by this same wrapper.
export function DashboardSection<T>({
  title,
  query,
  isEmpty,
  emptyMessage,
  children,
}: DashboardSectionProps<T>) {
  return (
    <section className="rounded border p-4">
      <h2 className="mb-3 text-sm font-semibold text-gray-700">{title}</h2>

      {query.isLoading && (
        <>
          <div className="h-32 animate-pulse rounded bg-gray-100" aria-hidden="true" />
          <p role="status" className="sr-only">
            Loading {title}…
          </p>
        </>
      )}

      {query.isError && (
        <div role="alert" className="space-y-2">
          <p className="text-sm text-red-700">{describeError(query.error)}</p>
          <button
            type="button"
            onClick={() => query.refetch()}
            className="rounded border px-3 py-1.5 text-sm"
          >
            Retry
          </button>
        </div>
      )}

      {query.data !== undefined &&
        !query.isError &&
        (isEmpty?.(query.data) ? (
          <p className="text-sm text-gray-500">{emptyMessage ?? "No data for this range."}</p>
        ) : (
          children(query.data)
        ))}
    </section>
  );
}
