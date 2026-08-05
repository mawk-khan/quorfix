"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { ApiError } from "@/lib/api/client";
import { listProjects } from "@/lib/api/projects";
import type { ArchivedFilter } from "@/lib/api/types";
import { useSession } from "@/lib/auth/session-provider";

import { PaginationControls } from "./pagination-controls";
import { ProjectFilters } from "./project-filters";
import { ProjectTable } from "./project-table";

function isArchivedFilter(value: string | null): value is ArchivedFilter {
  return value === "true" || value === "false" || value === "all";
}

function describeError(error: unknown): string {
  if (
    error instanceof ApiError &&
    typeof error.body === "object" &&
    error.body !== null &&
    "detail" in error.body
  ) {
    return String((error.body as { detail: unknown }).detail);
  }
  return "Something went wrong loading projects.";
}

export default function ProjectsPage() {
  return (
    // useSearchParams() opts this page out of static prerendering unless
    // it's wrapped in Suspense — the fallback only ever flashes during the
    // initial static shell render, not during normal client navigation.
    <Suspense
      fallback={
        <main className="p-8">
          <p>Loading projects…</p>
        </main>
      }
    >
      <ProjectsPageContent />
    </Suspense>
  );
}

function ProjectsPageContent() {
  const { session, isLoading: sessionLoading } = useSession();
  const isAdmin = session?.role === "administrator";
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const search = searchParams.get("search") ?? "";
  const archivedParam = searchParams.get("archived");
  const archived: ArchivedFilter = isArchivedFilter(archivedParam) ? archivedParam : "false";
  const page = Number(searchParams.get("page") ?? "1") || 1;

  function updateParams(next: Partial<{ search: string; archived: ArchivedFilter; page: number }>) {
    const params = new URLSearchParams(searchParams.toString());
    if (next.search !== undefined) {
      if (next.search) params.set("search", next.search);
      else params.delete("search");
    }
    if (next.archived !== undefined) {
      if (next.archived === "false") params.delete("archived");
      else params.set("archived", next.archived);
    }
    if (next.page !== undefined) {
      if (next.page <= 1) params.delete("page");
      else params.set("page", String(next.page));
    }
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  const projectsQuery = useQuery({
    // "list" vs "detail" keeps this query key from prefix-matching the
    // ["projects", "detail", id] key the detail page uses — invalidating
    // one must not force a refetch of the other.
    queryKey: ["projects", "list", { search, archived, page }],
    queryFn: () => listProjects({ search: search || undefined, archived, page }),
    enabled: !!session?.authenticated,
  });

  if (sessionLoading) {
    return (
      <main className="p-8">
        <p>Loading projects…</p>
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

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Projects</h1>
        {isAdmin && (
          <Link href="/projects/new" className="rounded bg-black px-3 py-2 text-sm text-white">
            New project
          </Link>
        )}
      </div>

      <ProjectFilters
        search={search}
        archived={archived}
        onSearchChange={(value) => updateParams({ search: value, page: 1 })}
        onArchivedChange={(value) => updateParams({ archived: value, page: 1 })}
      />

      {projectsQuery.isLoading && <p>Loading…</p>}

      {projectsQuery.isError && (
        <p role="alert" className="text-sm text-red-700">
          {describeError(projectsQuery.error)}
        </p>
      )}

      {projectsQuery.data && (
        <>
          <ProjectTable
            projects={projectsQuery.data.results}
            hasActiveFilters={!!search || archived !== "false"}
          />
          <PaginationControls
            count={projectsQuery.data.count}
            currentPage={page}
            onPageChange={(nextPage) => updateParams({ page: nextPage })}
          />
        </>
      )}
    </main>
  );
}
