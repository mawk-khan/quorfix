"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

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
  /** Muted line under the title — e.g. "Current backlog, not affected by
   * the date range" — rendered by CardHeader, not by each chart's own
   * markup, so every card's header looks identical. */
  subtitle?: ReactNode;
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
  subtitle,
  query,
  isEmpty,
  emptyMessage,
  children,
}: DashboardSectionProps<T>) {
  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} />
      <CardContent>
        {query.isLoading && (
          <>
            <Skeleton className="h-32" />
            <p role="status" className="sr-only">
              Loading {title}…
            </p>
          </>
        )}

        {query.isError && (
          <div role="alert" className="space-y-2">
            <p className="text-sm text-danger">{describeError(query.error)}</p>
            <Button type="button" variant="secondary" size="sm" onClick={() => query.refetch()}>
              Retry
            </Button>
          </div>
        )}

        {query.data !== undefined &&
          !query.isError &&
          (isEmpty?.(query.data) ? (
            <p className="text-sm text-text-secondary">{emptyMessage ?? "No data for this range."}</p>
          ) : (
            children(query.data)
          ))}
      </CardContent>
    </Card>
  );
}
