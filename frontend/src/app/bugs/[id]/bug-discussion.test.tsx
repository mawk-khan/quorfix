import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/comments", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/comments")>("@/lib/api/comments");
  return {
    ...actual,
    listComments: vi.fn(),
    createComment: vi.fn(),
    updateComment: vi.fn(),
    deleteComment: vi.fn(),
    redactComment: vi.fn(),
  };
});
vi.mock("@/lib/api/members", () => ({
  listMembers: vi.fn().mockResolvedValue([]),
}));

import { createComment, listComments } from "@/lib/api/comments";
import { ApiError } from "@/lib/api/client";
import type { Comment, PaginatedResponse } from "@/lib/api/types";
import { BugDiscussion } from "./bug-discussion";

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function paginated(results: Comment[]): PaginatedResponse<Comment> {
  return { count: results.length, next: null, previous: null, results };
}

function makeComment(overrides: Partial<Comment> = {}): Comment {
  return {
    id: "c1",
    author: { id: "u1", email: "dev@example.com", first_name: "Dev", last_name: "Eloper" },
    body: "First comment.",
    status: "active",
    mentions: [],
    edited_at: null,
    deleted_at: null,
    redacted_at: null,
    can_edit: false,
    can_delete: false,
    can_redact: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("BugDiscussion", () => {
  beforeEach(() => {
    vi.mocked(listComments).mockReset();
    vi.mocked(createComment).mockReset();
  });

  it("shows a loading state, then the empty state", async () => {
    vi.mocked(listComments).mockResolvedValueOnce(paginated([]));
    renderWithClient(<BugDiscussion bugId="b1" isArchived={false} canComment={true} />);

    expect(screen.getByText(/loading discussion/i)).toBeInTheDocument();
    expect(await screen.findByText(/no comments yet/i)).toBeInTheDocument();
  });

  it("shows an error state with a working retry", async () => {
    vi.mocked(listComments).mockRejectedValueOnce(new Error("boom"));
    vi.mocked(listComments).mockResolvedValueOnce(paginated([makeComment()]));
    renderWithClient(<BugDiscussion bugId="b1" isArchived={false} canComment={true} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load the discussion/i);
    await userEvent.setup().click(screen.getByRole("button", { name: /retry/i }));

    expect(await screen.findByText("First comment.")).toBeInTheDocument();
  });

  it("renders loaded comments oldest-first as returned by the backend", async () => {
    vi.mocked(listComments).mockResolvedValueOnce(paginated([makeComment({ id: "c1", body: "Oldest" }), makeComment({ id: "c2", body: "Newest" })]));
    renderWithClient(<BugDiscussion bugId="b1" isArchived={false} canComment={true} />);

    const items = await screen.findAllByTestId("comment-item");
    expect(items[0]).toHaveTextContent("Oldest");
    expect(items[1]).toHaveTextContent("Newest");
  });

  it("viewer sees the discussion but no comment form", async () => {
    vi.mocked(listComments).mockResolvedValueOnce(paginated([makeComment()]));
    renderWithClient(<BugDiscussion bugId="b1" isArchived={false} canComment={false} />);

    await screen.findByText("First comment.");
    expect(screen.queryByRole("form", { name: /add comment/i })).not.toBeInTheDocument();
    expect(screen.getByText(/viewers can read the discussion/i)).toBeInTheDocument();
  });

  it("shows a read-only explanation when the bug is archived, without a comment form", async () => {
    vi.mocked(listComments).mockResolvedValueOnce(paginated([]));
    renderWithClient(<BugDiscussion bugId="b1" isArchived={true} canComment={true} />);

    await screen.findByText(/no comments yet/i);
    expect(screen.queryByRole("form", { name: /add comment/i })).not.toBeInTheDocument();
    expect(screen.getByText(/archived, so new comments cannot be added/i)).toBeInTheDocument();
  });

  it("rejects an empty submission client-side without calling the API", async () => {
    vi.mocked(listComments).mockResolvedValueOnce(paginated([]));
    renderWithClient(<BugDiscussion bugId="b1" isArchived={false} canComment={true} />);
    const user = userEvent.setup();

    await screen.findByRole("form", { name: /add comment/i });
    await user.click(screen.getByRole("button", { name: /post comment/i }));

    expect(await screen.findByText(/comment cannot be empty/i)).toBeInTheDocument();
    expect(createComment).not.toHaveBeenCalled();
  });

  it("creates a comment, clears the form on success, and disables the button while pending", async () => {
    // Sticky (not "Once"): success invalidates the comments query, which
    // triggers a refetch on top of the initial load — both calls should
    // resolve the same way here.
    vi.mocked(listComments).mockResolvedValue(paginated([]));
    let resolveCreate: (value: Comment) => void = () => {};
    vi.mocked(createComment).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveCreate = resolve;
      }),
    );
    renderWithClient(<BugDiscussion bugId="b1" isArchived={false} canComment={true} />);
    const user = userEvent.setup();

    await screen.findByRole("form", { name: /add comment/i });
    const textarea = screen.getByLabelText(/comment/i, { selector: "textarea" });
    await user.type(textarea, "A brand new comment");
    const submit = screen.getByRole("button", { name: /post comment/i });
    await user.click(submit);

    // Duplicate submission is prevented while the mutation is in flight.
    await waitFor(() => expect(submit).toBeDisabled());
    resolveCreate(makeComment({ id: "new", body: "A brand new comment" }));

    await waitFor(() => expect(createComment).toHaveBeenCalledWith("b1", "A brand new comment"));
    await waitFor(() => expect((textarea as HTMLTextAreaElement).value).toBe(""));
  });

  it("preserves the draft text after a failed submission", async () => {
    vi.mocked(listComments).mockResolvedValueOnce(paginated([]));
    vi.mocked(createComment).mockRejectedValueOnce(new ApiError(409, { detail: "This bug is archived." }));
    renderWithClient(<BugDiscussion bugId="b1" isArchived={false} canComment={true} />);
    const user = userEvent.setup();

    await screen.findByRole("form", { name: /add comment/i });
    const textarea = screen.getByLabelText(/comment/i, { selector: "textarea" });
    await user.type(textarea, "please don't disappear");
    await user.click(screen.getByRole("button", { name: /post comment/i }));

    expect(await screen.findByText(/this bug is archived/i)).toBeInTheDocument();
    expect((textarea as HTMLTextAreaElement).value).toBe("please don't disappear");
  });
});
