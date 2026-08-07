"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Distributions } from "@/lib/api/types";
import { CHART_COLORS } from "@/lib/dashboard/chart-colors";
import { formatCount, formatStatusLabel } from "@/lib/dashboard/format";

import { DashboardSection } from "./dashboard-section";
import { VisuallyHiddenTable } from "./visually-hidden-table";

interface StatusDistributionChartProps {
  query: Pick<UseQueryResult<Distributions>, "data" | "isLoading" | "isError" | "error" | "refetch">;
}

export function StatusDistributionChart({ query }: StatusDistributionChartProps) {
  return (
    <DashboardSection
      title="Bugs by status"
      subtitle="Current backlog — not affected by the date range"
      query={query}
      isEmpty={(data) => data.status.every((row) => row.count === 0)}
      emptyMessage="No bugs in the current backlog."
    >
      {(distributions) => {
        const rows = distributions.status.map((row) => ({
          label: formatStatusLabel(row.status),
          count: row.count,
        }));

        return (
          <div aria-label="Current backlog, distribution of bug statuses — a current snapshot, unaffected by the date filter">
            <ResponsiveContainer width="100%" height={Math.max(240, rows.length * 32)}>
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
                  tick={{ fill: CHART_COLORS.textSecondary, fontSize: 12 }}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={100}
                  stroke={CHART_COLORS.axis}
                  tick={{ fill: CHART_COLORS.textSecondary, fontSize: 12 }}
                />
                <Tooltip
                  formatter={(value) => [formatCount(Number(value)), "Bugs"]}
                  contentStyle={{
                    background: CHART_COLORS.surface,
                    border: `1px solid ${CHART_COLORS.grid}`,
                    fontSize: 12,
                  }}
                  itemStyle={{ color: CHART_COLORS.textPrimary }}
                  labelStyle={{ color: CHART_COLORS.textPrimary }}
                />
                <Bar
                  dataKey="count"
                  name="Bugs"
                  fill={CHART_COLORS.singleMeasure}
                  radius={[0, 4, 4, 0]}
                  maxBarSize={20}
                />
              </BarChart>
            </ResponsiveContainer>
            <VisuallyHiddenTable
              caption="Current bugs by status"
              headers={["Status", "Bugs"]}
              rows={rows.map((row) => [row.label, row.count])}
            />
          </div>
        );
      }}
    </DashboardSection>
  );
}
