// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Drawer } from "./Drawer";

function noop() {
  /* no-op */
}

describe("Drawer", () => {
  it("renders nothing visible when closed (data-open=false, aria-hidden=true)", () => {
    const { container } = render(
      <Drawer open={false} onClose={noop} ariaLabel="Test drawer">
        <button type="button">First focusable</button>
      </Drawer>,
    );
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.getAttribute("data-open")).toBe("false");
    expect(wrapper.getAttribute("aria-hidden")).toBe("true");
  });

  it("renders dialog with role + aria-modal + aria-label when open", () => {
    render(
      <Drawer open={true} onClose={noop} ariaLabel="Test drawer">
        <button type="button">First focusable</button>
      </Drawer>,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-label")).toBe("Test drawer");
  });

  it("uses the spec'd default width of 480px when width prop omitted", () => {
    render(
      <Drawer open={true} onClose={noop} ariaLabel="Test drawer">
        <button type="button">A</button>
      </Drawer>,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog.style.width).toBe("480px");
  });

  it("honors a custom width prop", () => {
    render(
      <Drawer open={true} onClose={noop} ariaLabel="Test drawer" width={720}>
        <button type="button">A</button>
      </Drawer>,
    );
    expect(screen.getByRole("dialog").style.width).toBe("720px");
  });

  it("ESC key invokes onClose", () => {
    const onClose = vi.fn();
    render(
      <Drawer open={true} onClose={onClose} ariaLabel="Test drawer">
        <button type="button">A</button>
      </Drawer>,
    );
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("backdrop click invokes onClose", () => {
    const onClose = vi.fn();
    const { container } = render(
      <Drawer open={true} onClose={onClose} ariaLabel="Test drawer">
        <button type="button">A</button>
      </Drawer>,
    );
    // Backdrop is the first button inside the wrapper, marked aria-hidden.
    const backdrop = container.querySelector('button[aria-hidden="true"]') as HTMLElement;
    expect(backdrop).not.toBeNull();
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("moves focus into the dialog when opened", () => {
    const { rerender } = render(
      <Drawer open={false} onClose={noop} ariaLabel="Test drawer">
        <button type="button" data-testid="first">First focusable</button>
        <button type="button">Second</button>
      </Drawer>,
    );
    rerender(
      <Drawer open={true} onClose={noop} ariaLabel="Test drawer">
        <button type="button" data-testid="first">First focusable</button>
        <button type="button">Second</button>
      </Drawer>,
    );
    expect(document.activeElement).toBe(screen.getByTestId("first"));
  });

  it("locks body scroll while open and restores on close", () => {
    document.body.style.overflow = "";
    const { rerender, unmount } = render(
      <Drawer open={false} onClose={noop} ariaLabel="Test drawer">
        <button type="button">A</button>
      </Drawer>,
    );
    expect(document.body.style.overflow).toBe("");
    rerender(
      <Drawer open={true} onClose={noop} ariaLabel="Test drawer">
        <button type="button">A</button>
      </Drawer>,
    );
    expect(document.body.style.overflow).toBe("hidden");
    rerender(
      <Drawer open={false} onClose={noop} ariaLabel="Test drawer">
        <button type="button">A</button>
      </Drawer>,
    );
    expect(document.body.style.overflow).toBe("");
    unmount();
  });

  it("Tab from last focusable cycles back to first (forward trap)", () => {
    render(
      <Drawer open={true} onClose={noop} ariaLabel="Test drawer">
        <button type="button" data-testid="first">First</button>
        <button type="button" data-testid="last">Last</button>
      </Drawer>,
    );
    const last = screen.getByTestId("last");
    last.focus();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Tab" });
    expect(document.activeElement).toBe(screen.getByTestId("first"));
  });

  it("Shift+Tab from first focusable cycles to last (reverse trap)", () => {
    render(
      <Drawer open={true} onClose={noop} ariaLabel="Test drawer">
        <button type="button" data-testid="first">First</button>
        <button type="button" data-testid="last">Last</button>
      </Drawer>,
    );
    const first = screen.getByTestId("first");
    first.focus();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(screen.getByTestId("last"));
  });
});
