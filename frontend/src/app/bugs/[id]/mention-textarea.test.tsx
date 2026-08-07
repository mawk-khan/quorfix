import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import type { Membership } from "@/lib/api/types";

import { MentionTextarea } from "./mention-textarea";

const MEMBERS: Membership[] = [
  {
    id: "m1",
    user: { id: "u1", email: "ada@example.com", first_name: "Ada", last_name: "Lovelace" },
    role: "developer",
    joined_at: new Date().toISOString(),
  },
  {
    id: "m2",
    user: { id: "u2", email: "bob@example.com", first_name: "Bob", last_name: "Builder" },
    role: "qa",
    joined_at: new Date().toISOString(),
  },
];

function Harness() {
  const [value, setValue] = useState("");
  return (
    <div>
      <MentionTextarea value={value} onChange={setValue} members={MEMBERS} aria-label="Comment" />
      <output data-testid="value">{value}</output>
    </div>
  );
}

describe("MentionTextarea", () => {
  it("opens suggestions when typing @ and filters as more is typed", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const textarea = screen.getByLabelText("Comment");

    await user.type(textarea, "hey @");
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(2);

    await user.type(textarea, "bo");
    expect(screen.getAllByRole("option")).toHaveLength(1);
    expect(screen.getByRole("option")).toHaveTextContent("Bob Builder");
  });

  it("Escape closes the popover", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const textarea = screen.getByLabelText("Comment");

    await user.type(textarea, "@");
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("ArrowDown/ArrowUp navigate and Enter inserts the structured token", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const textarea = screen.getByLabelText("Comment");

    await user.type(textarea, "@");
    await screen.findByRole("listbox");
    await user.keyboard("{ArrowDown}"); // move to Bob
    await user.keyboard("{Enter}");

    expect(screen.getByTestId("value")).toHaveTextContent("@[Bob Builder](mention:u2)");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("mouse selection inserts the structured token", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const textarea = screen.getByLabelText("Comment");

    await user.type(textarea, "@ada");
    const option = await screen.findByRole("option", { name: /ada lovelace/i });
    await user.click(option);

    expect(screen.getByTestId("value")).toHaveTextContent("@[Ada Lovelace](mention:u1)");
  });

  it("wires the editable-combobox ARIA relationship correctly (role, aria-expanded/controls/activedescendant, aria-selected)", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const textarea = screen.getByLabelText("Comment");

    // Closed state: combobox role present, nothing claims to be expanded or
    // to own/point at a listbox that doesn't exist yet.
    expect(textarea).toHaveAttribute("role", "combobox");
    expect(textarea).toHaveAttribute("aria-autocomplete", "list");
    expect(textarea).toHaveAttribute("aria-expanded", "false");
    expect(textarea).not.toHaveAttribute("aria-controls");
    expect(textarea).not.toHaveAttribute("aria-activedescendant");

    await user.type(textarea, "@");
    const listbox = await screen.findByRole("listbox");
    const options = screen.getAllByRole("option");

    // Open state: aria-controls must resolve to the listbox actually in the
    // DOM, and aria-activedescendant must resolve to the currently-active
    // option — both are id references, so assert the target exists and
    // matches, not just that some string is present.
    expect(textarea).toHaveAttribute("aria-expanded", "true");
    expect(textarea).toHaveAttribute("aria-controls", listbox.id);
    expect(textarea).toHaveAttribute("aria-activedescendant", options[0]!.id);
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    expect(options[1]).toHaveAttribute("aria-selected", "false");

    // ArrowDown moves the active option — aria-activedescendant and
    // aria-selected must move with it (this is what lets a screen reader
    // announce the newly-active option without moving real focus off the
    // textarea, per the WAI-ARIA APG editable-combobox pattern).
    await user.keyboard("{ArrowDown}");
    expect(textarea).toHaveAttribute("aria-activedescendant", options[1]!.id);
    expect(options[0]).toHaveAttribute("aria-selected", "false");
    expect(options[1]).toHaveAttribute("aria-selected", "true");
  });

  it("does not insert a second token when the same user is mentioned again", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const textarea = screen.getByLabelText("Comment");

    await user.type(textarea, "@ada");
    await user.click(await screen.findByRole("option", { name: /ada lovelace/i }));
    const firstValue = screen.getByTestId("value").textContent ?? "";
    expect(firstValue).toBe("@[Ada Lovelace](mention:u1) ");

    // Regression coverage: selecting a mention moves the caret to just past
    // the inserted token so immediately typing more continues from there,
    // in order, rather than the caret jumping elsewhere mid-keystroke and
    // scrambling the characters (see mention-textarea.tsx's insertMention/
    // useLayoutEffect for why this was previously a real race, not just a
    // test timing issue).
    await user.type(textarea, "@ada");
    expect(screen.getByTestId("value")).toHaveTextContent("@[Ada Lovelace](mention:u1) @ada");
    await user.click(await screen.findByRole("option", { name: /ada lovelace/i }));
    const secondValue = screen.getByTestId("value").textContent ?? "";
    expect(secondValue).toBe("@[Ada Lovelace](mention:u1) ");
  });
});
