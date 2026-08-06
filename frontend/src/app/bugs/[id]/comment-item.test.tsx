import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/comments", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/comments")>("@/lib/api/comments");
  return {
    ...actual,
    updateComment: vi.fn(),
    deleteComment: vi.fn(),
    redactComment: vi.fn(),
  };
});

import { deleteComment, redactComment, updateComment } from "@/lib/api/comments";
import { ApiError } from "@/lib/api/client";
import type { Comment, Membership } from "@/lib/api/types";
import { CommentItem } from "./comment-item";

const MEMBERS: Membership[] = [];

function makeComment(overrides: Partial<Comment> = {}): Comment {
  return {
    id: "c1",
    author: { id: "u1", email: "dev@example.com", first_name: "Dev", last_name: "Eloper" },
    body: "Looks good to me.",
    status: "active",
    mentions: [],
    edited_at: null,
    deleted_at: null,
    redacted_at: null,
    can_edit: true,
    can_delete: true,
    can_redact: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("CommentItem", () => {
  beforeEach(() => {
    vi.mocked(updateComment).mockReset();
    vi.mocked(deleteComment).mockReset();
    vi.mocked(redactComment).mockReset();
  });

  it("shows edit/delete only when can_edit/can_delete are true, and redact only when can_redact", () => {
    render(
      <ul>
        <CommentItem
          bugId="b1"
          comment={makeComment({ can_edit: true, can_delete: true, can_redact: false })}
          members={MEMBERS}
          onMutated={vi.fn()}
          onStaleState={vi.fn()}
        />
      </ul>,
    );
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^redact$/i })).not.toBeInTheDocument();
  });

  it("opens an inline edit form, preserves the original value on cancel", async () => {
    const user = userEvent.setup();
    render(
      <ul>
        <CommentItem bugId="b1" comment={makeComment()} members={MEMBERS} onMutated={vi.fn()} onStaleState={vi.fn()} />
      </ul>,
    );

    await user.click(screen.getByRole("button", { name: /^edit$/i }));
    const textarea = screen.getByLabelText(/edit comment/i);
    await user.clear(textarea);
    await user.type(textarea, "changed my mind");
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(screen.queryByLabelText(/edit comment/i)).not.toBeInTheDocument();
    expect(screen.getByText("Looks good to me.")).toBeInTheDocument();
    // The MentionTextarea unmounted along with the rest of edit mode —
    // focus must land back on the Edit button, not fall through to body.
    expect(screen.getByRole("button", { name: /^edit$/i })).toHaveFocus();
  });

  it("submits an edit and calls onMutated with the server response", async () => {
    const user = userEvent.setup();
    const onMutated = vi.fn();
    const updated = makeComment({ body: "Updated body", edited_at: new Date().toISOString() });
    vi.mocked(updateComment).mockResolvedValueOnce(updated);
    render(
      <ul>
        <CommentItem bugId="b1" comment={makeComment()} members={MEMBERS} onMutated={onMutated} onStaleState={vi.fn()} />
      </ul>,
    );

    await user.click(screen.getByRole("button", { name: /^edit$/i }));
    const textarea = screen.getByLabelText(/edit comment/i);
    await user.clear(textarea);
    await user.type(textarea, "Updated body");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(updateComment).toHaveBeenCalledWith("b1", "c1", "Updated body"));
    await waitFor(() => expect(onMutated).toHaveBeenCalledWith(updated));
    expect(screen.getByRole("button", { name: /^edit$/i })).toHaveFocus();
  });

  it("on a 409 edit-window-expired error, shows the backend message, closes the edit form, and refreshes stale state", async () => {
    const user = userEvent.setup();
    const onStaleState = vi.fn();
    vi.mocked(updateComment).mockRejectedValueOnce(
      new ApiError(409, { detail: "The edit window for this comment has passed." }),
    );
    render(
      <ul>
        <CommentItem bugId="b1" comment={makeComment()} members={MEMBERS} onMutated={vi.fn()} onStaleState={onStaleState} />
      </ul>,
    );

    await user.click(screen.getByRole("button", { name: /^edit$/i }));
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/edit window.*has passed/i);
    expect(screen.queryByLabelText(/edit comment/i)).not.toBeInTheDocument();
    // The cached can_edit hint may now be stale (that's exactly why this
    // request 409'd) — the comment list must be refetched, not left as-is.
    expect(onStaleState).toHaveBeenCalled();
  });

  it("on a 403 error, shows the backend message and refreshes stale state", async () => {
    const user = userEvent.setup();
    const onStaleState = vi.fn();
    vi.mocked(updateComment).mockRejectedValueOnce(
      new ApiError(403, { detail: "You do not have permission to perform this action." }),
    );
    render(
      <ul>
        <CommentItem bugId="b1" comment={makeComment()} members={MEMBERS} onMutated={vi.fn()} onStaleState={onStaleState} />
      </ul>,
    );

    await user.click(screen.getByRole("button", { name: /^edit$/i }));
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/do not have permission/i);
    expect(onStaleState).toHaveBeenCalled();
  });

  it("requires confirmation before deleting, then calls onMutated with the placeholder", async () => {
    const user = userEvent.setup();
    const onMutated = vi.fn();
    const deleted = makeComment({ status: "deleted", body: "", deleted_at: new Date().toISOString() });
    vi.mocked(deleteComment).mockResolvedValueOnce(deleted);
    render(
      <ul>
        <CommentItem bugId="b1" comment={makeComment()} members={MEMBERS} onMutated={onMutated} onStaleState={vi.fn()} />
      </ul>,
    );

    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(deleteComment).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /confirm delete/i }));

    await waitFor(() => expect(onMutated).toHaveBeenCalledWith(deleted));
  });

  it("on a delete conflict (already deleted/redacted), shows the backend message and refreshes stale state", async () => {
    const user = userEvent.setup();
    const onStaleState = vi.fn();
    vi.mocked(deleteComment).mockRejectedValueOnce(
      new ApiError(409, { detail: "This comment has already been deleted or redacted." }),
    );
    render(
      <ul>
        <CommentItem bugId="b1" comment={makeComment()} members={MEMBERS} onMutated={vi.fn()} onStaleState={onStaleState} />
      </ul>,
    );

    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    await user.click(screen.getByRole("button", { name: /confirm delete/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/already been deleted or redacted/i);
    expect(onStaleState).toHaveBeenCalled();
  });

  it("redact requires confirmation, uses explicit moderation wording, and calls onMutated", async () => {
    const user = userEvent.setup();
    const onMutated = vi.fn();
    const redacted = makeComment({ status: "redacted", body: "", redacted_at: new Date().toISOString(), can_redact: true });
    vi.mocked(redactComment).mockResolvedValueOnce(redacted);
    render(
      <ul>
        <CommentItem
          bugId="b1"
          comment={makeComment({ can_redact: true })}
          members={MEMBERS}
          onMutated={onMutated}
          onStaleState={vi.fn()}
        />
      </ul>,
    );

    await user.click(screen.getByRole("button", { name: /^redact$/i }));
    expect(screen.getByText(/permanently removed/i)).toBeInTheDocument();
    expect(screen.getByText(/moderation record will remain/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /confirm redact/i }));

    await waitFor(() => expect(onMutated).toHaveBeenCalledWith(redacted));
  });

  it("on a redact conflict, shows the backend message and refreshes stale state", async () => {
    const user = userEvent.setup();
    const onStaleState = vi.fn();
    vi.mocked(redactComment).mockRejectedValueOnce(
      new ApiError(409, { detail: "This comment has already been deleted or redacted." }),
    );
    render(
      <ul>
        <CommentItem
          bugId="b1"
          comment={makeComment({ can_redact: true })}
          members={MEMBERS}
          onMutated={vi.fn()}
          onStaleState={onStaleState}
        />
      </ul>,
    );

    await user.click(screen.getByRole("button", { name: /^redact$/i }));
    await user.click(screen.getByRole("button", { name: /confirm redact/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/already been deleted or redacted/i);
    expect(onStaleState).toHaveBeenCalled();
  });

  it("renders the deleted placeholder instead of the (possibly stale) cached body", () => {
    render(
      <ul>
        <CommentItem
          bugId="b1"
          comment={makeComment({ status: "deleted", body: "" })}
          members={MEMBERS}
          onMutated={vi.fn()}
          onStaleState={vi.fn()}
        />
      </ul>,
    );
    expect(screen.getByTestId("comment-placeholder")).toHaveTextContent(/this comment was deleted/i);
    expect(screen.queryByText("Looks good to me.")).not.toBeInTheDocument();
  });

  it("renders the redacted placeholder distinctly from the deleted one", () => {
    render(
      <ul>
        <CommentItem
          bugId="b1"
          comment={makeComment({ status: "redacted", body: "" })}
          members={MEMBERS}
          onMutated={vi.fn()}
          onStaleState={vi.fn()}
        />
      </ul>,
    );
    expect(screen.getByTestId("comment-placeholder")).toHaveTextContent(/redacted by an administrator/i);
  });

  it("renders mention tokens safely in an active comment body", () => {
    render(
      <ul>
        <CommentItem
          bugId="b1"
          comment={makeComment({ body: "hey @[Ada](mention:11111111-1111-1111-1111-111111111111)" })}
          members={MEMBERS}
          onMutated={vi.fn()}
          onStaleState={vi.fn()}
        />
      </ul>,
    );
    expect(screen.getByTestId("mention-token")).toHaveTextContent("@Ada");
  });
});
