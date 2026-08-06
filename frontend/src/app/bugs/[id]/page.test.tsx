import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type { Bug, Session } from "@/lib/api/types";
import { renderWithProviders } from "@/test-utils";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "b1" }),
}));

vi.mock("@/lib/api/auth", () => ({
  getSession: vi.fn(),
}));
vi.mock("@/lib/api/members", () => ({
  listMembers: vi.fn().mockResolvedValue([]),
}));
vi.mock("@/lib/api/bugs", async () => {
  // activityKeys is a plain query-key helper (no network I/O) consumed by
  // bug-activity-feed.tsx and bug-relationships-panel.tsx — keep the real
  // implementation rather than a stub so their queryKey shapes stay valid
  // under this mock.
  const actual = await vi.importActual<typeof import("@/lib/api/bugs")>("@/lib/api/bugs");
  return {
    activityKeys: actual.activityKeys,
    getBug: vi.fn(),
    updateBug: vi.fn(),
    transitionBug: vi.fn(),
    assignBug: vi.fn(),
    archiveBug: vi.fn(),
    restoreBug: vi.fn(),
    addTag: vi.fn(),
    removeTag: vi.fn(),
    watchBug: vi.fn(),
    unwatchBug: vi.fn(),
    listBugActivity: vi.fn().mockResolvedValue({ count: 0, next: null, previous: null, results: [] }),
    listBugs: vi.fn().mockResolvedValue({ count: 0, next: null, previous: null, results: [] }),
    addRelationship: vi.fn(),
    removeRelationship: vi.fn(),
  };
});
vi.mock("@/lib/api/comments", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/comments")>("@/lib/api/comments");
  return {
    commentKeys: actual.commentKeys,
    buildMentionToken: actual.buildMentionToken,
    listComments: vi.fn().mockResolvedValue({ count: 0, next: null, previous: null, results: [] }),
    createComment: vi.fn(),
    updateComment: vi.fn(),
    deleteComment: vi.fn(),
    redactComment: vi.fn(),
  };
});
vi.mock("@/lib/api/attachments", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/attachments")>("@/lib/api/attachments");
  return {
    attachmentKeys: actual.attachmentKeys,
    ALLOWED_ATTACHMENT_CONTENT_TYPES: actual.ALLOWED_ATTACHMENT_CONTENT_TYPES,
    MAX_ATTACHMENT_SIZE_BYTES: actual.MAX_ATTACHMENT_SIZE_BYTES,
    formatFileSize: actual.formatFileSize,
    listAttachments: vi.fn().mockResolvedValue({ count: 0, next: null, previous: null, results: [] }),
    initiateAttachmentUpload: vi.fn(),
    uploadAttachmentBytes: vi.fn(),
    downloadAttachment: vi.fn(),
    removeAttachment: vi.fn(),
  };
});

import { getSession } from "@/lib/api/auth";
import { archiveBug, getBug, updateBug } from "@/lib/api/bugs";
import { listAttachments } from "@/lib/api/attachments";
import { listComments } from "@/lib/api/comments";
import BugDetailPage from "./page";

function mockSession(role: Session["role"]): void {
  vi.mocked(getSession).mockResolvedValue({
    authenticated: true,
    role,
    user: { id: "me", email: "me@example.com", first_name: "Me", last_name: "" },
    organization: { id: "org1", name: "Acme", slug: "acme" },
  });
}

function makeBug(overrides: Partial<Bug> = {}): Bug {
  return {
    id: "b1",
    key: "ENG-1",
    number: 1,
    project: { id: "p1", key: "ENG", name: "Engine" },
    title: "Login button unresponsive",
    description: "It just doesn't work.",
    steps_to_reproduce: "",
    expected_result: "",
    actual_result: "",
    environment: "",
    category: "",
    status: "new",
    priority: "high",
    severity: "major",
    reporter: { id: "reporter1", email: "reporter@example.com", first_name: "Rep", last_name: "" },
    assignee: null,
    due_date: null,
    resolved_at: null,
    closed_at: null,
    archived_at: null,
    version: 1,
    tags: [],
    watcher_count: 0,
    is_watching: false,
    available_transitions: ["triaged"],
    editable_fields: [],
    can_assign: false,
    can_archive: false,
    can_manage_relationships: false,
    relationships: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("BugDetailPage", () => {
  it("shows read-only content and no mutation controls for a viewer", async () => {
    mockSession("viewer");
    vi.mocked(getBug).mockResolvedValueOnce(makeBug());
    renderWithProviders(<BugDetailPage />);

    expect(await screen.findByText("It just doesn't work.")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: /edit bug/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/^archive bug$/i)).not.toBeInTheDocument();
    // Watching is available to every member, viewer included.
    expect(screen.getByRole("button", { name: /^watch$/i })).toBeInTheDocument();
  });

  it("shows an editable form and archive control for an administrator", async () => {
    mockSession("administrator");
    vi.mocked(getBug).mockResolvedValueOnce(
      makeBug({
        editable_fields: ["title", "description", "priority", "severity"],
        can_assign: true,
        can_archive: true,
      }),
    );
    renderWithProviders(<BugDetailPage />);

    expect(await screen.findByRole("form", { name: /edit bug/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^archive bug$/i })).toBeInTheDocument();
  });

  it("submits a content edit", async () => {
    mockSession("administrator");
    const bug = makeBug({ editable_fields: ["title", "description"] });
    vi.mocked(getBug).mockResolvedValueOnce(bug);
    vi.mocked(updateBug).mockResolvedValueOnce({ ...bug, title: "Renamed", version: 2 });
    renderWithProviders(<BugDetailPage />);
    const user = userEvent.setup();

    await screen.findByRole("form", { name: /edit bug/i });
    const titleInput = screen.getByLabelText(/^title$/i);
    await user.clear(titleInput);
    await user.type(titleInput, "Renamed");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() =>
      expect(updateBug).toHaveBeenCalledWith(
        "b1",
        expect.objectContaining({ version: 1, title: "Renamed" }),
      ),
    );
  });

  it("does not send fields the viewer cannot edit", async () => {
    mockSession("administrator");
    const bug = makeBug({ editable_fields: ["title"] }); // priority/severity NOT editable here
    vi.mocked(getBug).mockResolvedValueOnce(bug);
    vi.mocked(updateBug).mockResolvedValueOnce(bug);
    renderWithProviders(<BugDetailPage />);
    const user = userEvent.setup();

    await screen.findByRole("form", { name: /edit bug/i });
    expect(screen.queryByLabelText(/^priority$/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(updateBug).toHaveBeenCalled());
    const call = vi.mocked(updateBug).mock.calls[0];
    const payload = call?.[1] as unknown as Record<string, unknown>;
    expect(payload).not.toHaveProperty("priority");
    expect(payload).not.toHaveProperty("severity");
  });

  it("requires confirmation before archiving", async () => {
    mockSession("administrator");
    const bug = makeBug({ can_archive: true });
    vi.mocked(getBug).mockResolvedValueOnce(bug);
    vi.mocked(archiveBug).mockResolvedValueOnce({ ...bug, archived_at: new Date().toISOString() });
    renderWithProviders(<BugDetailPage />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /^archive bug$/i }));
    expect(screen.getByText(/archive this bug\?/i)).toBeInTheDocument();
    expect(archiveBug).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /confirm/i }));
    await waitFor(() => expect(archiveBug).toHaveBeenCalledWith("b1", 1));
  });

  it("hides mutation controls and shows a note for an archived bug", async () => {
    mockSession("administrator");
    vi.mocked(getBug).mockResolvedValueOnce(
      makeBug({ archived_at: new Date().toISOString(), can_archive: true, editable_fields: ["title"] }),
    );
    renderWithProviders(<BugDetailPage />);

    expect(await screen.findByText(/archived and cannot be edited/i)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: /edit bug/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /restore bug/i })).toBeInTheDocument();
  });

  it("shows a version-conflict banner and lets the user reload the latest version", async () => {
    mockSession("administrator");
    const bug = makeBug({ editable_fields: ["title"] });
    vi.mocked(getBug).mockResolvedValueOnce(bug);
    const latest = { ...bug, title: "Changed by someone else", version: 5 };
    vi.mocked(updateBug).mockRejectedValueOnce(
      new ApiError(409, {
        code: "bug_version_conflict",
        detail: "This bug was changed by someone else since you last loaded it.",
        bug: latest,
      }),
    );
    renderWithProviders(<BugDetailPage />);
    const user = userEvent.setup();

    await screen.findByRole("form", { name: /edit bug/i });
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText(/changed by someone else since you loaded it/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /reload latest version/i }));

    expect(await screen.findByText("Changed by someone else")).toBeInTheDocument();
  });

  it("shows an unauthorized-not-found state for a bug outside the caller's organization", async () => {
    mockSession("administrator");
    vi.mocked(getBug).mockRejectedValueOnce(new ApiError(404, { detail: "Not found." }));
    renderWithProviders(<BugDetailPage />);

    expect(await screen.findByRole("heading", { name: /not found/i })).toBeInTheDocument();
    expect(screen.getByText(/does not exist or you don't have access/i)).toBeInTheDocument();
  });

  it("renders the new attachments/discussion sections alongside existing controls without duplicate bug fetches", async () => {
    mockSession("administrator");
    // This file's other tests don't reset mocks between cases (each relies
    // only on its own mockResolvedValueOnce), so getBug's call count
    // accumulates across the whole file — assert the *increase* caused by
    // this render, not an absolute count.
    const getBugCallsBefore = vi.mocked(getBug).mock.calls.length;
    vi.mocked(getBug).mockResolvedValueOnce(makeBug({ editable_fields: ["title"], can_archive: true }));
    renderWithProviders(<BugDetailPage />);

    await screen.findByRole("form", { name: /edit bug/i });
    expect(await screen.findByRole("heading", { name: /attachments/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /discussion/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /activity/i })).toBeInTheDocument();

    // Pre-existing controls (archive) still work with the new sections mounted.
    expect(screen.getByRole("button", { name: /^archive bug$/i })).toBeInTheDocument();
    expect(listComments).toHaveBeenCalledWith("b1", 1);
    expect(listAttachments).toHaveBeenCalledWith("b1", 1);
    expect(vi.mocked(getBug).mock.calls.length - getBugCallsBefore).toBe(1);
  });
});
