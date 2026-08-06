"use client";

import type { UseQueryResult } from "@tanstack/react-query";

import type { AnalyticsSummary } from "@/lib/api/types";
import { formatCount } from "@/lib/dashboard/format";

import { DashboardSection } from "./dashboard-section";

interface SummaryCardsProps {
  query: Pick<UseQueryResult<AnalyticsSummary>, "data" | "isLoading" | "isError" | "error" | "refetch">;
}

const CARDS: { key: keyof AnalyticsSummary; label: string; hint: string }[] = [
  { key: "open_bugs", label: "Total open bugs", hint: "Current, ignores the date range" },
  { key: "overdue_bugs", label: "Overdue bugs", hint: "Current, ignores the date range" },
  { key: "new_bugs", label: "New bugs", hint: "In the selected range" },
  { key: "resolved_bugs", label: "Resolved bugs", hint: "In the selected range" },
];

export function SummaryCards({ query }: SummaryCardsProps) {
  return (
    <DashboardSection title="Summary" query={query}>
      {(summary) => (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {CARDS.map((card) => (
            <div key={card.key} className="rounded border p-4">
              <p className="text-xs text-gray-500">{card.label}</p>
              <p
                className="mt-1 text-2xl font-semibold text-gray-900"
                data-testid={`summary-${card.key}`}
              >
                {formatCount(summary[card.key])}
              </p>
              <p className="mt-1 text-xs text-gray-500">{card.hint}</p>
            </div>
          ))}
        </div>
      )}
    </DashboardSection>
  );
}
