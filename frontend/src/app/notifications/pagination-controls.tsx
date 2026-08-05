"use client";

// Matches BoundedPageNumberPagination's default page_size (apps/core/pagination.py) —
// mirrors app/bugs/pagination-controls.tsx and app/projects/pagination-controls.tsx.
export const NOTIFICATIONS_PAGE_SIZE = 25;

interface PaginationControlsProps {
  count: number;
  currentPage: number;
  onPageChange: (page: number) => void;
}

export function PaginationControls({ count, currentPage, onPageChange }: PaginationControlsProps) {
  const totalPages = Math.max(1, Math.ceil(count / NOTIFICATIONS_PAGE_SIZE));

  if (totalPages <= 1) {
    return null;
  }

  return (
    <nav aria-label="Pagination" className="flex items-center justify-between text-sm">
      <button
        type="button"
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage <= 1}
        className="rounded border px-3 py-1 disabled:opacity-50"
      >
        Previous
      </button>
      <span aria-live="polite">
        Page {currentPage} of {totalPages}
      </span>
      <button
        type="button"
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage >= totalPages}
        className="rounded border px-3 py-1 disabled:opacity-50"
      >
        Next
      </button>
    </nav>
  );
}
