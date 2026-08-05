"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { ResolutionTimeEntry } from "@/lib/api/types";
import { CHART_COLORS } from "@/lib/dashboard/chart-colors";
import { formatDuration } from "@/lib/dashboard/format";

import { DashboardSection } from "./dashboard-section";
import { VisuallyHiddenTable } from "./visually-hidden-table";

interface ResolutionTimeChartProps {
  query: Pick<
    UseQueryResult<ResolutionTimeEntry[]>,
    "data" | "isLoading" | "isError" | "error" | "refetch"
  >;
}

const PRIORITY_LABELS: Record<string, string> = {
  urgent: "Urgent",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export function ResolutionTimeChart({ query }: ResolutionTimeChartProps) {
  return (
    <DashboardSection
      title="Average resolution time by priority"
      query={query}
      isEmpty={(data) => data.every((entry) => entry.average_seconds === null)}
      emptyMessage="No bugs resolved in this range have stayed resolved — nothing to average yet."
    >
      {(entries) => {
        const chartData = entries.map((entry) => ({
          priority: PRIORITY_LABELS[entry.priority] ?? entry.priority,
          seconds: entry.average_seconds ?? 0,
          hasData: entry.average_seconds !== null,
        }));

        return (
          <div aria-label="Average resolution time in the selected range, by priority">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
                <XAxis
                  dataKey="priority"
                  stroke={CHART_COLORS.axis}
                  tick={{ fill: CHART_COLORS.textMuted, fontSize: 12 }}
                />
                <YAxis
                  tickFormatter={(value: number) => formatDuration(value)}
                  stroke={CHART_COLORS.axis}
                  tick={{ fill: CHART_COLORS.textMuted, fontSize: 12 }}
                />
                <Tooltip
                  formatter={(value, _name, item) => [
                    (item?.payload as { hasData?: boolean } | undefined)?.hasData
                      ? formatDuration(Number(value))
                      : "No data",
                    "Average resolution time",
                  ]}
                  contentStyle={{
                    background: CHART_COLORS.surface,
                    border: `1px solid ${CHART_COLORS.grid}`,
                    fontSize: 12,
                  }}
                />
                <Bar
                  dataKey="seconds"
                  name="Average resolution time"
                  fill={CHART_COLORS.singleMeasure}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={48}
                />
              </BarChart>
            </ResponsiveContainer>
            <VisuallyHiddenTable
              caption="Average resolution time by priority"
              headers={["Priority", "Average resolution time"]}
              rows={entries.map((entry) => [
                PRIORITY_LABELS[entry.priority] ?? entry.priority,
                formatDuration(entry.average_seconds),
              ])}
            />
          </div>
        );
      }}
    </DashboardSection>
  );
}
