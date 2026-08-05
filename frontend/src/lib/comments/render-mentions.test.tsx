import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderCommentBody } from "./render-mentions";

describe("renderCommentBody", () => {
  it("renders plain text unchanged", () => {
    render(<p>{renderCommentBody("just a normal comment")}</p>);
    expect(screen.getByText("just a normal comment")).toBeInTheDocument();
  });

  it("renders a valid mention token as a styled mention, not the raw source", () => {
    render(
      <p>
        {renderCommentBody("hey @[Ada Lovelace](mention:11111111-1111-1111-1111-111111111111) can you look?")}
      </p>,
    );
    const mention = screen.getByTestId("mention-token");
    expect(mention).toHaveTextContent("@Ada Lovelace");
    expect(screen.queryByText(/mention:11111111/)).not.toBeInTheDocument();
  });

  it("renders a token with a non-UUID id segment as harmless plain text", () => {
    render(<p>{renderCommentBody("hey @[Fake](mention:not-a-real-uuid-not-a-real-uuid)")}</p>);
    expect(screen.queryByTestId("mention-token")).not.toBeInTheDocument();
    expect(screen.getByText(/@\[Fake\]\(mention:not-a-real-uuid-not-a-real-uuid\)/)).toBeInTheDocument();
  });

  it("never interprets HTML-like content in the body — it always renders as inert text", () => {
    const { container } = render(<p>{renderCommentBody('<script>alert("x")</script> plain text')}</p>);
    expect(container.querySelector("script")).not.toBeInTheDocument();
    expect(screen.getByText(/plain text/)).toBeInTheDocument();
  });

  it("handles multiple mentions in one body", () => {
    render(
      <p>
        {renderCommentBody(
          "@[Ada](mention:11111111-1111-1111-1111-111111111111) and @[Bob](mention:22222222-2222-2222-2222-222222222222)",
        )}
      </p>,
    );
    expect(screen.getAllByTestId("mention-token")).toHaveLength(2);
  });
});
