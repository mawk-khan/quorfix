"use client";

import { Button } from "@/components/ui/button";

// Matches BoundedPageNumberPagination's default page_size (apps/core/pagination.py).
// This phase doesn't expose a client-controlled page size, so it's a fixed constant.
export const PROJECTS_PAGE_SIZE = 25;

interface PaginationControlsProps {
  count: number;
  currentPage: number;
  onPageChange: (page: number) => void;
}

export function PaginationControls({ count, currentPage, onPageChange }: PaginationControlsProps) {
  // Total pages is derived from count + the fixed page size, not from
  // presence/absence of next/previous links, so "page X of Y" and disabled
  // states stay correct even when navigating by typing a URL directly.
  const totalPages = Math.max(1, Math.ceil(count / PROJECTS_PAGE_SIZE));

  if (totalPages <= 1) {
    return null;
  }

  return (
    <nav aria-label="Pagination" className="flex items-center justify-between text-sm">
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage <= 1}
      >
        Previous
      </Button>
      <span aria-live="polite" className="text-text-secondary">
        Page {currentPage} of {totalPages}
      </span>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage >= totalPages}
      >
        Next
      </Button>
    </nav>
  );
}
