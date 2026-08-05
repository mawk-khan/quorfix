import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/attachments", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/attachments")>("@/lib/api/attachments");
  return {
    ...actual,
    initiateAttachmentUpload: vi.fn(),
    uploadAttachmentBytes: vi.fn(),
  };
});

import { ApiError } from "@/lib/api/client";
import { initiateAttachmentUpload, uploadAttachmentBytes } from "@/lib/api/attachments";
import type { Attachment } from "@/lib/api/types";
import { AttachmentUpload } from "./attachment-upload";

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
    size_bytes: 12,
    status: "uploaded",
    scan_status: "not_scanned",
    uploaded_at: new Date().toISOString(),
    removed_at: null,
    can_remove: true,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

function selectFile(file: File) {
  const input = screen.getByLabelText(/upload attachment/i) as HTMLInputElement;
  return userEvent.upload(input, file);
}

describe("AttachmentUpload", () => {
  beforeEach(() => {
    vi.mocked(initiateAttachmentUpload).mockReset();
    vi.mocked(uploadAttachmentBytes).mockReset();
  });

  it("shows a disabled explanation instead of the upload control when disabled (e.g. archived)", () => {
    renderWithClient(
      <AttachmentUpload bugId="b1" disabled disabledReason="This bug is archived, so attachments cannot be added." persistedAttachmentIds={new Set()} />,
    );
    expect(screen.getByText(/archived, so attachments cannot be added/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/upload attachment/i)).not.toBeInTheDocument();
  });

  it("rejects a disallowed content type client-side without calling the API", async () => {
    renderWithClient(<AttachmentUpload bugId="b1" disabled={false} persistedAttachmentIds={new Set()} />);
    const file = new File(["bad"], "malware.exe", { type: "application/x-msdownload" });

    await selectFile(file);

    expect(await screen.findByRole("alert")).toHaveTextContent(/not an accepted file type/i);
    expect(initiateAttachmentUpload).not.toHaveBeenCalled();
  });

  it("explicitly rejects SVG files client-side", async () => {
    renderWithClient(<AttachmentUpload bugId="b1" disabled={false} persistedAttachmentIds={new Set()} />);
    const file = new File(["<svg></svg>"], "icon.svg", { type: "image/svg+xml" });

    await selectFile(file);

    expect(await screen.findByRole("alert")).toHaveTextContent(/not an accepted file type/i);
    expect(initiateAttachmentUpload).not.toHaveBeenCalled();
  });

  it("rejects a file over the 10 MB limit client-side", async () => {
    renderWithClient(<AttachmentUpload bugId="b1" disabled={false} persistedAttachmentIds={new Set()} />);
    const file = new File([new Uint8Array(1)], "big.png", { type: "image/png" });
    Object.defineProperty(file, "size", { value: 11 * 1024 * 1024 });

    await selectFile(file);

    expect(await screen.findByRole("alert")).toHaveTextContent(/larger than the 10 mb limit/i);
    expect(initiateAttachmentUpload).not.toHaveBeenCalled();
  });

  it("uploads an accepted file through the two-step flow and shows progress", async () => {
    const attachment = makeAttachment();
    vi.mocked(initiateAttachmentUpload).mockResolvedValueOnce({
      attachment: { ...attachment, status: "pending" },
      upload: { method: "PUT", url: "/api/attachments/a1/upload-bytes/" },
    });
    let resolveUpload: (value: Attachment) => void = () => {};
    vi.mocked(uploadAttachmentBytes).mockImplementationOnce(
      (_url, _file, options) =>
        new Promise((resolve) => {
          options?.onProgress?.(0.5);
          resolveUpload = resolve;
        }),
    );

    renderWithClient(<AttachmentUpload bugId="b1" disabled={false} persistedAttachmentIds={new Set()} />);
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });
    await selectFile(file);

    await waitFor(() =>
      expect(initiateAttachmentUpload).toHaveBeenCalledWith("b1", {
        original_filename: "notes.txt",
        content_type: "text/plain",
        size_bytes: file.size,
      }),
    );
    expect(await screen.findByText(/uploading… 50%/i)).toBeInTheDocument();

    resolveUpload(attachment);
    expect(await screen.findByText(/^uploaded$/i)).toBeInTheDocument();
  });

  it("on failure, shows an error and retry that starts a fresh upload rather than reusing the failed row", async () => {
    vi.mocked(initiateAttachmentUpload).mockResolvedValueOnce({
      attachment: { ...makeAttachment(), status: "pending" },
      upload: { method: "PUT", url: "/api/attachments/a1/upload-bytes/" },
    });
    vi.mocked(uploadAttachmentBytes).mockRejectedValueOnce(new ApiError(409, { detail: "The uploaded file did not match the declared size." }));

    renderWithClient(<AttachmentUpload bugId="b1" disabled={false} persistedAttachmentIds={new Set()} />);
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });
    await selectFile(file);

    expect(await screen.findByRole("alert")).toHaveTextContent(/did not match the declared size/i);
    expect(uploadAttachmentBytes).toHaveBeenCalledTimes(1);

    // Retry: a fresh initiate + upload cycle, never a second upload-bytes
    // call against the failed row's original attachment id.
    vi.mocked(initiateAttachmentUpload).mockResolvedValueOnce({
      attachment: { ...makeAttachment({ id: "a2" }), status: "pending" },
      upload: { method: "PUT", url: "/api/attachments/a2/upload-bytes/" },
    });
    vi.mocked(uploadAttachmentBytes).mockResolvedValueOnce(makeAttachment({ id: "a2" }));

    await userEvent.setup().click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => expect(initiateAttachmentUpload).toHaveBeenCalledTimes(2));
    expect(uploadAttachmentBytes).toHaveBeenCalledTimes(2);
    expect(await screen.findByText(/^uploaded$/i)).toBeInTheDocument();
  });

  it("removes the temporary row once the persisted attachment id appears in the confirmed list", async () => {
    const attachment = makeAttachment({ id: "a1" });
    vi.mocked(initiateAttachmentUpload).mockResolvedValueOnce({
      attachment: { ...attachment, status: "pending" },
      upload: { method: "PUT", url: "/api/attachments/a1/upload-bytes/" },
    });
    vi.mocked(uploadAttachmentBytes).mockResolvedValueOnce(attachment);

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <AttachmentUpload bugId="b1" disabled={false} persistedAttachmentIds={new Set()} />
      </QueryClientProvider>,
    );
    const file = new File(["hello"], "notes.txt", { type: "text/plain" });
    await selectFile(file);

    expect(await screen.findByText(/^uploaded$/i)).toBeInTheDocument();
    expect(screen.getByTestId("upload-row")).toBeInTheDocument();

    rerender(
      <QueryClientProvider client={queryClient}>
        <AttachmentUpload bugId="b1" disabled={false} persistedAttachmentIds={new Set(["a1"])} />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.queryByTestId("upload-row")).not.toBeInTheDocument());
  });
});
