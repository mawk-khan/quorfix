"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TrendPoint } from "@/lib/api/types";
import { CHART_COLORS } from "@/lib/dashboard/chart-colors";
import { formatShortDate } from "@/lib/dashboard/format";

import { DashboardSection } from "./dashboard-section";
import { VisuallyHiddenTable } from "./visually-hidden-table";

interface BugTrendsChartProps {
  query: Pick<UseQueryResult<TrendPoint[]>, "data" | "isLoading" | "isError" | "error" | "refetch">;
}

export function BugTrendsChart({ query }: BugTrendsChartProps) {
  return (
    <DashboardSection
      title="Bug trends"
      query={query}
      isEmpty={(data) => data.every((point) => point.created === 0 && point.resolved === 0)}
      emptyMessage="No bugs were created or resolved in this range."
    >
      {(points) => (
        <div aria-label="Bugs created and resolved per day for the selected range">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={formatShortDate}
                stroke={CHART_COLORS.axis}
                tick={{ fill: CHART_COLORS.textMuted, fontSize: 12 }}
              />
              <YAxis
                allowDecimals={false}
                stroke={CHART_COLORS.axis}
                tick={{ fill: CHART_COLORS.textMuted, fontSize: 12 }}
              />
              <Tooltip
                labelFormatter={(value) => formatShortDate(String(value))}
                contentStyle={{
                  background: CHART_COLORS.surface,
                  border: `1px solid ${CHART_COLORS.grid}`,
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line
                type="monotone"
                dataKey="created"
                name="Created"
                stroke={CHART_COLORS.seriesCreated}
                strokeWidth={2}
                dot={{ r: 3, strokeWidth: 2, stroke: CHART_COLORS.surface }}
              />
              <Line
                type="monotone"
                dataKey="resolved"
                name="Resolved"
                stroke={CHART_COLORS.seriesResolved}
                strokeWidth={2}
                strokeDasharray="6 3"
                dot={{ r: 3, strokeWidth: 2, stroke: CHART_COLORS.surface }}
              />
            </LineChart>
          </ResponsiveContainer>
          <VisuallyHiddenTable
            caption="Bugs created and resolved per day"
            headers={["Date", "Created", "Resolved"]}
            rows={points.map((point) => [formatShortDate(point.date), point.created, point.resolved])}
          />
        </div>
      )}
    </DashboardSection>
  );
}
