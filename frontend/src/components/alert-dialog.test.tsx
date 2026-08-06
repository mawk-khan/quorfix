import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { AlertDialog } from "./alert-dialog";

// Mirrors every real call site (comment-item.tsx, attachment-list.tsx, the
// bug/project archive sections): the trigger button and the dialog are
// mutually exclusive siblings — the button unmounts the instant the dialog
// mounts, not merely hidden alongside it. This is what makes restoreFocusTo
// (a ref captured by the caller) necessary in the first place: by the time
// AlertDialog's own effects run, the trigger is already gone from the DOM.
function renderWithTrigger(props: Partial<React.ComponentProps<typeof AlertDialog>> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();

  function Harness() {
    const [open, setOpen] = useState(false);
    const triggerRef = useRef<HTMLButtonElement>(null);
    return (
      <div>
        {!open && (
          <button ref={triggerRef} type="button" onClick={() => setOpen(true)}>
            Open dialog
          </button>
        )}
        {open && (
          <AlertDialog
            title="Confirm thing"
            description="Are you sure?"
            confirmLabel="Confirm"
            onConfirm={() => {
              onConfirm();
              setOpen(false);
            }}
            onCancel={() => {
              onCancel();
              setOpen(false);
            }}
            restoreFocusTo={triggerRef}
            {...props}
          />
        )}
      </div>
    );
  }

  render(<Harness />);
  return { onConfirm, onCancel };
}

describe("AlertDialog", () => {
  it("has alertdialog role, aria-modal, and labelled/described-by text", async () => {
    const user = userEvent.setup();
    renderWithTrigger();
    await user.click(screen.getByRole("button", { name: "Open dialog" }));

    const dialog = screen.getByRole("alertdialog", { name: "Confirm thing" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleDescription("Are you sure?");
  });

  it("moves initial focus to Cancel, not the destructive Confirm button", async () => {
    const user = userEvent.setup();
    renderWithTrigger();
    await user.click(screen.getByRole("button", { name: "Open dialog" }));

    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  it("traps Tab within the dialog's own controls", async () => {
    const user = userEvent.setup();
    renderWithTrigger();
    await user.click(screen.getByRole("button", { name: "Open dialog" }));

    const cancelButton = screen.getByRole("button", { name: "Cancel" });
    const confirmButton = screen.getByRole("button", { name: "Confirm" });
    expect(cancelButton).toHaveFocus();

    await user.tab();
    expect(confirmButton).toHaveFocus();

    // Wraps back to Cancel instead of escaping to "Open dialog".
    await user.tab();
    expect(cancelButton).toHaveFocus();

    // Shift+Tab from the first control wraps to the last.
    await user.tab({ shift: true });
    expect(confirmButton).toHaveFocus();
  });

  it("closes on Escape and calls onCancel, unless a request is pending", async () => {
    const user = userEvent.setup();
    const { onCancel } = renderWithTrigger();
    await user.click(screen.getByRole("button", { name: "Open dialog" }));

    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("ignores Escape while pending", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();

    function Harness() {
      return (
        <AlertDialog
          title="Confirm thing"
          description="Are you sure?"
          confirmLabel="Confirm"
          onConfirm={vi.fn()}
          onCancel={onCancel}
          pending
        />
      );
    }

    render(<Harness />);
    await user.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("restores focus to the triggering element on cancel, even though the trigger unmounts when the dialog opens", async () => {
    const user = userEvent.setup();
    renderWithTrigger();
    const trigger = screen.getByRole("button", { name: "Open dialog" });
    await user.click(trigger);
    expect(screen.queryByRole("button", { name: "Open dialog" })).not.toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Open dialog" })).toHaveFocus();
  });

  it("restores focus to the triggering element after a successful confirm", async () => {
    const user = userEvent.setup();
    renderWithTrigger();
    await user.click(screen.getByRole("button", { name: "Open dialog" }));

    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(screen.getByRole("button", { name: "Open dialog" })).toHaveFocus();
  });

  it("falls back gracefully when no restoreFocusTo is given (still closes, no crash)", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(
      <AlertDialog
        title="Confirm thing"
        description="Are you sure?"
        confirmLabel="Confirm"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );

    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("disables both buttons while pending", () => {
    render(
      <AlertDialog
        title="Confirm thing"
        description="Are you sure?"
        confirmLabel="Confirm"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        pending
      />,
    );
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
  });
});
