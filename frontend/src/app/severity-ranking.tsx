"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Distributions } from "@/lib/api/types";
import { CHART_COLORS } from "@/lib/dashboard/chart-colors";
import { formatCount, formatStatusLabel } from "@/lib/dashboard/format";

import { DashboardSection } from "./dashboard-section";
import { VisuallyHiddenTable } from "./visually-hidden-table";

interface SeverityRankingProps {
  query: Pick<UseQueryResult<Distributions>, "data" | "isLoading" | "isError" | "error" | "refetch">;
}

export function SeverityRanking({ query }: SeverityRankingProps) {
  return (
    <DashboardSection
      title="Bugs by severity"
      query={query}
      isEmpty={(data) => data.severity.every((row) => row.count === 0)}
      emptyMessage="No bugs in the current backlog."
    >
      {(distributions) => {
        // Already ranked blocker -> trivial by the backend (BugSeverity's
        // declaration order) — never re-sorted here.
        const rows = distributions.severity.map((row) => ({
          label: formatStatusLabel(row.severity),
          count: row.count,
        }));

        return (
          <div aria-label="Current backlog, ranked from most to least severe — a current snapshot, unaffected by the date filter">
            <p className="mb-2 text-xs text-gray-400">
              Current backlog, ranked blocker to trivial — not affected by the date range
            </p>
            <ResponsiveContainer width="100%" height={Math.max(180, rows.length * 36)}>
              <BarChart
                data={rows}
                layout="vertical"
                margin={{ top: 4, right: 24, left: 8, bottom: 4 }}
              >
                <CartesianGrid stroke={CHART_COLORS.grid} horizontal={false} />
                <XAxis
                  type="number"
                  allowDecimals={false}
                  stroke={CHART_COLORS.axis}
                  tick={{ fill: CHART_COLORS.textMuted, fontSize: 12 }}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={80}
                  stroke={CHART_COLORS.axis}
                  tick={{ fill: CHART_COLORS.textMuted, fontSize: 12 }}
                />
                <Tooltip
                  formatter={(value) => [formatCount(Number(value)), "Bugs"]}
                  contentStyle={{
                    background: CHART_COLORS.surface,
                    border: `1px solid ${CHART_COLORS.grid}`,
                    fontSize: 12,
                  }}
                />
                <Bar
                  dataKey="count"
                  name="Bugs"
                  fill={CHART_COLORS.singleMeasure}
                  radius={[0, 4, 4, 0]}
                  maxBarSize={24}
                />
              </BarChart>
            </ResponsiveContainer>
            <VisuallyHiddenTable
              caption="Current bugs by severity, ranked blocker to trivial"
              headers={["Severity", "Bugs"]}
              rows={rows.map((row) => [row.label, row.count])}
            />
          </div>
        );
      }}
    </DashboardSection>
  );
}
