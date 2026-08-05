import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/attachments", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/attachments")>("@/lib/api/attachments");
  return {
    ...actual,
    downloadAttachment: vi.fn(),
    removeAttachment: vi.fn(),
  };
});

import { ApiError } from "@/lib/api/client";
import { downloadAttachment, removeAttachment } from "@/lib/api/attachments";
import type { Attachment } from "@/lib/api/types";
import { AttachmentList } from "./attachment-list";

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function makeAttachment(overrides: Partial<Attachment> = {}): Attachment {
  return {
    id: "a1",
    uploaded_by: { id: "u1", email: "dev@example.com", first_name: "Dev", last_name: "Eloper" },
    original_filename: "notes.txt",
    content_type: "text/plain",
    size_bytes: 2048,
    status: "uploaded",
    scan_status: "clean",
    uploaded_at: new Date().toISOString(),
    removed_at: null,
    can_remove: true,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("AttachmentList", () => {
  beforeEach(() => {
    vi.mocked(downloadAttachment).mockReset();
    vi.mocked(removeAttachment).mockReset();
  });

  it("shows an empty state when there are no attachments", () => {
    renderWithClient(<AttachmentList bugId="b1" attachments={[]} />);
    expect(screen.getByText(/no attachments yet/i)).toBeInTheDocument();
  });

  it("shows filename, size, uploader, and scan status", () => {
    renderWithClient(<AttachmentList bugId="b1" attachments={[makeAttachment()]} />);
    expect(screen.getByText("notes.txt")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
    expect(screen.getByText(/uploaded by dev eloper/i)).toBeInTheDocument();
    expect(screen.getByText("Clean")).toBeInTheDocument();
  });

  it("downloads an attachment", async () => {
    vi.mocked(downloadAttachment).mockResolvedValueOnce(undefined);
    renderWithClient(<AttachmentList bugId="b1" attachments={[makeAttachment()]} />);

    await userEvent.setup().click(screen.getByRole("button", { name: /^download$/i }));

    await waitFor(() => expect(downloadAttachment).toHaveBeenCalledWith("b1", "a1", "notes.txt"));
  });

  it("shows a graceful message when the file is missing (404)", async () => {
    vi.mocked(downloadAttachment).mockRejectedValueOnce(new ApiError(404, { detail: "Not found." }));
    renderWithClient(<AttachmentList bugId="b1" attachments={[makeAttachment()]} />);

    await userEvent.setup().click(screen.getByRole("button", { name: /^download$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/no longer available/i);
  });

  it("only shows remove when can_remove is true", () => {
    renderWithClient(<AttachmentList bugId="b1" attachments={[makeAttachment({ can_remove: false })]} />);
    expect(screen.queryByRole("button", { name: /^remove$/i })).not.toBeInTheDocument();
  });

  it("requires confirmation before removing, then removes it immediately from the visible list", async () => {
    vi.mocked(removeAttachment).mockResolvedValueOnce(makeAttachment({ removed_at: new Date().toISOString() }));
    renderWithClient(<AttachmentList bugId="b1" attachments={[makeAttachment()]} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /^remove$/i }));
    expect(removeAttachment).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /confirm remove/i }));

    await waitFor(() => expect(screen.queryByText("notes.txt")).not.toBeInTheDocument());
  });

  it("on a 403/409 removal error, shows the backend message rather than removing the row", async () => {
    vi.mocked(removeAttachment).mockRejectedValueOnce(new ApiError(409, { detail: "This attachment has already been removed." }));
    renderWithClient(<AttachmentList bugId="b1" attachments={[makeAttachment()]} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /^remove$/i }));
    await user.click(screen.getByRole("button", { name: /confirm remove/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/already been removed/i);
    expect(screen.getByText("notes.txt")).toBeInTheDocument();
  });
});
