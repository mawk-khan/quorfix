"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { listBugs } from "@/lib/api/bugs";
import { ApiError } from "@/lib/api/client";
import { listProjects } from "@/lib/api/projects";
import { useSession } from "@/lib/auth/session-provider";

import { BugFilters, type BugFiltersValue } from "./bug-filters";
import { BugTable } from "./bug-table";
import { PaginationControls } from "./pagination-controls";

function describeError(error: unknown): string {
  if (
    error instanceof ApiError &&
    typeof error.body === "object" &&
    error.body !== null &&
    "detail" in error.body
  ) {
    return String((error.body as { detail: unknown }).detail);
  }
  return "Something went wrong loading bugs.";
}

export default function BugsPage() {
  return (
    // useSearchParams() opts this page out of static prerendering unless
    // wrapped in Suspense — matches the pattern in app/projects/page.tsx.
    <Suspense
      fallback={
        <main className="p-8">
          <p>Loading bugs…</p>
        </main>
      }
    >
      <BugsPageContent />
    </Suspense>
  );
}

function BugsPageContent() {
  const { session, isLoading: sessionLoading } = useSession();
  const canCreate = session?.role !== null && session?.role !== "viewer";
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const filters: BugFiltersValue = {
    search: searchParams.get("search") ?? "",
    status: searchParams.get("status")?.split(",").filter(Boolean) ?? [],
    priority: searchParams.get("priority") ?? "",
    severity: searchParams.get("severity") ?? "",
    project: searchParams.get("project") ?? "",
    archived:
      (searchParams.get("archived") as BugFiltersValue["archived"] | null) &&
      ["true", "false", "all"].includes(searchParams.get("archived")!)
        ? (searchParams.get("archived") as BugFiltersValue["archived"])
        : "false",
    unassigned: searchParams.get("unassigned") === "true",
    ordering: searchParams.get("ordering") ?? "-created_at",
  };
  const page = Number(searchParams.get("page") ?? "1") || 1;

  function updateParams(next: Partial<BugFiltersValue> & { page?: number }) {
    const params = new URLSearchParams(searchParams.toString());
    const merged = { ...filters, ...next };

    if (merged.search) params.set("search", merged.search);
    else params.delete("search");

    if (merged.status.length) params.set("status", merged.status.join(","));
    else params.delete("status");

    if (merged.priority) params.set("priority", merged.priority);
    else params.delete("priority");

    if (merged.severity) params.set("severity", merged.severity);
    else params.delete("severity");

    if (merged.project) params.set("project", merged.project);
    else params.delete("project");

    if (merged.archived && merged.archived !== "false") params.set("archived", merged.archived);
    else params.delete("archived");

    if (merged.unassigned) params.set("unassigned", "true");
    else params.delete("unassigned");

    if (merged.ordering && merged.ordering !== "-created_at") params.set("ordering", merged.ordering);
    else params.delete("ordering");

    const nextPage = next.page ?? 1;
    if (nextPage > 1) params.set("page", String(nextPage));
    else params.delete("page");

    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  const projectsQuery = useQuery({
    queryKey: ["projects", "list", "for-bug-filters"],
    queryFn: () => listProjects({ archived: "false" }),
    enabled: !!session?.authenticated,
  });

  const bugsQuery = useQuery({
    queryKey: ["bugs", "list", { ...filters, page }],
    queryFn: () =>
      listBugs({
        search: filters.search || undefined,
        status: filters.status.length ? (filters.status as never) : undefined,
        priority: (filters.priority || undefined) as never,
        severity: (filters.severity || undefined) as never,
        project: filters.project || undefined,
        archived: filters.archived,
        unassigned: filters.unassigned || undefined,
        ordering: filters.ordering,
        page,
      }),
    enabled: !!session?.authenticated,
  });

  if (sessionLoading) {
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

  const hasActiveFilters =
    !!filters.search ||
    filters.status.length > 0 ||
    !!filters.priority ||
    !!filters.severity ||
    !!filters.project ||
    filters.archived !== "false" ||
    filters.unassigned;

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Bugs</h1>
        {canCreate && (
          <Link href="/bugs/new" className="rounded bg-black px-3 py-2 text-sm text-white">
            New bug
          </Link>
        )}
      </div>

      <BugFilters
        value={filters}
        projects={projectsQuery.data?.results ?? []}
        onChange={(next) => updateParams(next)}
      />

      {bugsQuery.isLoading && <p>Loading…</p>}

      {bugsQuery.isError && (
        <p role="alert" className="text-sm text-red-700">
          {describeError(bugsQuery.error)}
        </p>
      )}

      {bugsQuery.data && (
        <>
          <BugTable bugs={bugsQuery.data.results} hasActiveFilters={hasActiveFilters} />
          <PaginationControls
            count={bugsQuery.data.count}
            currentPage={page}
            onPageChange={(nextPage) => updateParams({ page: nextPage })}
          />
        </>
      )}
    </main>
  );
}
