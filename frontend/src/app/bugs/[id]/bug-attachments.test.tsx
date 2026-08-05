import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/attachments", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/attachments")>("@/lib/api/attachments");
  return {
    ...actual,
    listAttachments: vi.fn(),
  };
});

import { listAttachments } from "@/lib/api/attachments";
import type { Attachment, PaginatedResponse } from "@/lib/api/types";
import { BugAttachments } from "./bug-attachments";

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function paginated(results: Attachment[]): PaginatedResponse<Attachment> {
  return { count: results.length, next: null, previous: null, results };
}

describe("BugAttachments", () => {
  beforeEach(() => {
    vi.mocked(listAttachments).mockReset();
  });

  it("shows a loading state, then the empty state", async () => {
    vi.mocked(listAttachments).mockResolvedValueOnce(paginated([]));
    renderWithClient(<BugAttachments bugId="b1" isArchived={false} canUpload={true} />);

    expect(screen.getByText(/loading attachments/i)).toBeInTheDocument();
    expect(await screen.findByText(/no attachments yet/i)).toBeInTheDocument();
  });

  it("shows an error state with a working retry", async () => {
    vi.mocked(listAttachments).mockRejectedValueOnce(new Error("boom"));
    vi.mocked(listAttachments).mockResolvedValueOnce(paginated([]));
    renderWithClient(<BugAttachments bugId="b1" isArchived={false} canUpload={true} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load attachments/i);
    await userEvent.setup().click(screen.getByRole("button", { name: /retry/i }));

    expect(await screen.findByText(/no attachments yet/i)).toBeInTheDocument();
  });

  it("shows the upload control for an eligible role", async () => {
    vi.mocked(listAttachments).mockResolvedValueOnce(paginated([]));
    renderWithClient(<BugAttachments bugId="b1" isArchived={false} canUpload={true} />);

    expect(await screen.findByLabelText(/upload attachment/i)).toBeInTheDocument();
  });

  it("hides the upload control entirely for a viewer", async () => {
    vi.mocked(listAttachments).mockResolvedValueOnce(paginated([]));
    renderWithClient(<BugAttachments bugId="b1" isArchived={false} canUpload={false} />);

    await screen.findByText(/no attachments yet/i);
    expect(screen.queryByLabelText(/upload attachment/i)).not.toBeInTheDocument();
  });

  it("shows a disabled explanation instead of the upload control when the bug is archived", async () => {
    vi.mocked(listAttachments).mockResolvedValueOnce(paginated([]));
    renderWithClient(<BugAttachments bugId="b1" isArchived={true} canUpload={true} />);

    expect(await screen.findByText(/archived, so attachments cannot be added/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/upload attachment/i)).not.toBeInTheDocument();
  });
});
