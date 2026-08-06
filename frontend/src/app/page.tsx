"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Suspense } from "react";

import {
  analyticsKeys,
  getActiveProjects,
  getDistributions,
  getRecentActivity,
  getResolutionTime,
  getSummary,
  getTrends,
  getWorkload,
} from "@/lib/api/analytics";
import { useDashboardFilters } from "@/lib/dashboard/use-dashboard-filters";
import { useSession } from "@/lib/auth/session-provider";

import { ActiveProjectsPanel } from "./active-projects-panel";
import { BugTrendsChart } from "./bug-trends-chart";
import { DashboardFilters } from "./dashboard-filters";
import { DeveloperWorkload } from "./developer-workload";
import { RecentActivityFeed } from "./recent-activity-feed";
import { ResolutionTimeChart } from "./resolution-time-chart";
import { SeverityRanking } from "./severity-ranking";
import { StatusDistributionChart } from "./status-distribution-chart";
import { SummaryCards } from "./summary-cards";

export default function HomePage() {
  return (
    // useSearchParams() opts this page out of static prerendering unless
    // wrapped in Suspense — matches app/bugs/page.tsx and app/notifications/page.tsx.
    <Suspense
      fallback={
        <main id="main-content" tabIndex={-1} className="p-8">
          <p>Loading…</p>
        </main>
      }
    >
      <DashboardPageContent />
    </Suspense>
  );
}

function DashboardPageContent() {
  const { session, isLoading: sessionLoading } = useSession();
  const { ready, filters, updateFilters } = useDashboardFilters();

  const authenticated = !!session?.authenticated;
  const projectParam = filters.project || undefined;
  const rangeParams = { date_from: filters.date_from, date_to: filters.date_to, project: projectParam };
  const projectOnlyParams = { project: projectParam };

  // Active projects powers both the project filter dropdown and its own
  // panel — one query, not two, for the same organization-wide project list.
  const activeProjectsQuery = useQuery({
    queryKey: analyticsKeys.activeProjects(),
    queryFn: getActiveProjects,
    enabled: authenticated,
  });

  const summaryQuery = useQuery({
    queryKey: analyticsKeys.summary(rangeParams),
    queryFn: () => getSummary(rangeParams),
    enabled: authenticated && ready,
  });

  const trendsQuery = useQuery({
    queryKey: analyticsKeys.trends(rangeParams),
    queryFn: () => getTrends(rangeParams),
    enabled: authenticated && ready,
  });

  const resolutionTimeQuery = useQuery({
    queryKey: analyticsKeys.resolutionTime(rangeParams),
    queryFn: () => getResolutionTime(rangeParams),
    enabled: authenticated && ready,
  });

  // Distributions/workload/active-projects/recent-activity are current-state
  // snapshots (see docs/ACCESS_AND_TESTING.md) — they don't depend on `ready`
  // (no date range involved), so they load immediately, independent of the
  // preset-date resolution the ranged sections above wait on.
  const distributionsQuery = useQuery({
    queryKey: analyticsKeys.distributions(projectOnlyParams),
    queryFn: () => getDistributions(projectOnlyParams),
    enabled: authenticated,
  });

  const workloadQuery = useQuery({
    queryKey: analyticsKeys.workload(projectOnlyParams),
    queryFn: () => getWorkload(projectOnlyParams),
    enabled: authenticated,
  });

  const recentActivityParams = { ...projectOnlyParams, page_size: 10 };
  const recentActivityQuery = useQuery({
    queryKey: analyticsKeys.recentActivity(recentActivityParams),
    queryFn: () => getRecentActivity(recentActivityParams),
    enabled: authenticated,
  });

  if (sessionLoading) {
    return (
      <main id="main-content" tabIndex={-1} className="p-8">
        <p>Loading…</p>
      </main>
    );
  }

  if (!session?.authenticated) {
    return (
      <main id="main-content" tabIndex={-1} className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
        <h1 className="text-2xl font-semibold">Bug Fixer</h1>
        <Link href="/sign-in" className="underline">
          Sign in
        </Link>
      </main>
    );
  }

  return (
    <main id="main-content" tabIndex={-1} className="mx-auto max-w-6xl space-y-6 p-8">
      <h1 className="text-xl font-semibold">Dashboard</h1>

      <DashboardFilters
        filters={filters}
        projects={activeProjectsQuery.data ?? []}
        onChange={updateFilters}
      />

      {!ready ? (
        <div className="h-32 animate-pulse rounded bg-gray-100" aria-hidden="true" />
      ) : (
        <>
          <SummaryCards query={summaryQuery} />
          <div className="grid gap-6 lg:grid-cols-2">
            <BugTrendsChart query={trendsQuery} />
            <ResolutionTimeChart query={resolutionTimeQuery} />
          </div>
        </>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <StatusDistributionChart query={distributionsQuery} />
        <SeverityRanking query={distributionsQuery} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <DeveloperWorkload query={workloadQuery} />
        <ActiveProjectsPanel query={activeProjectsQuery} />
      </div>

      <RecentActivityFeed query={recentActivityQuery} />
    </main>
  );
}
