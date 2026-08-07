"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { Bug, CheckCircle2, Clock, Sparkles, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import type { AnalyticsSummary } from "@/lib/api/types";
import { formatCount } from "@/lib/dashboard/format";

interface SummaryCardsProps {
  query: Pick<UseQueryResult<AnalyticsSummary>, "data" | "isLoading" | "isError" | "error" | "refetch">;
}

const CARDS: {
  key: keyof AnalyticsSummary;
  label: string;
  hint: string;
  icon: LucideIcon;
  iconClassName: string;
}[] = [
  {
    key: "open_bugs",
    label: "Total open bugs",
    hint: "Current, ignores the date range",
    icon: Bug,
    iconClassName: "bg-blue-50 text-blue-600",
  },
  {
    key: "overdue_bugs",
    label: "Overdue bugs",
    hint: "Current, ignores the date range",
    icon: Clock,
    iconClassName: "bg-amber-50 text-amber-600",
  },
  {
    key: "new_bugs",
    label: "New bugs",
    hint: "In the selected range",
    icon: Sparkles,
    iconClassName: "bg-green-50 text-green-600",
  },
  {
    key: "resolved_bugs",
    label: "Resolved bugs",
    hint: "In the selected range",
    icon: CheckCircle2,
    iconClassName: "bg-purple-50 text-purple-600",
  },
];

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

// Four independent cards, not one card containing four cells (unlike every
// other dashboard panel) — this is what the visual reference shows for the
// summary row, and it reads better at a glance than one more-nested level.
export function SummaryCards({ query }: SummaryCardsProps) {
  if (query.isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4" aria-hidden="true">
        {CARDS.map((card) => (
          <Card key={card.key}>
            <CardContent>
              <Skeleton className="h-20" />
            </CardContent>
          </Card>
        ))}
        <p role="status" className="sr-only">
          Loading summary…
        </p>
      </div>
    );
  }

  if (query.isError) {
    return (
      <Card>
        <CardContent>
          <div role="alert" className="space-y-2">
            <p className="text-sm text-danger">{describeError(query.error)}</p>
            <Button type="button" variant="secondary" size="sm" onClick={() => query.refetch()}>
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (query.data === undefined) return null;
  const summary = query.data;

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {CARDS.map((card) => {
        const Icon = card.icon;
        return (
          <Card key={card.key}>
            <CardContent>
              <span
                aria-hidden="true"
                className={`inline-flex size-9 items-center justify-center rounded-field ${card.iconClassName}`}
              >
                <Icon className="size-[18px]" />
              </span>
              <p className="mt-3 text-xs text-text-secondary">{card.label}</p>
              <p
                className="mt-1 text-2xl font-semibold text-text-primary"
                data-testid={`summary-${card.key}`}
              >
                {formatCount(summary[card.key])}
              </p>
              <p className="mt-1 text-xs text-text-secondary">{card.hint}</p>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
