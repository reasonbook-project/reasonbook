// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useHelpStore } from "@/stores/help";

import { HelpLink } from "./HelpLink";

describe("HelpLink", () => {
  beforeEach(() => {
    useHelpStore.setState({ open: false, articleId: null });
  });

  afterEach(() => {
    useHelpStore.setState({ open: false, articleId: null });
  });

  it("opens the help drawer to the requested article when clicked (link variant)", () => {
    render(<HelpLink topic="decisions/finalize" />);
    expect(useHelpStore.getState().open).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: /Need help/i }));
    expect(useHelpStore.getState().open).toBe(true);
    expect(useHelpStore.getState().articleId).toBe("decisions/finalize");
  });

  it("renders the icon variant with the article title as the default aria-label", () => {
    render(<HelpLink topic="decisions/claim" variant="icon" />);
    // The icon variant looks up the article title (e.g. "Claiming a decision")
    // and uses it for both the tooltip and the aria-label — the topic slug
    // is too technical for users.
    const btn = screen.getByRole("button", { name: /Claiming a decision/i });
    fireEvent.click(btn);
    expect(useHelpStore.getState().articleId).toBe("decisions/claim");
  });

  it("honours a custom label on the link variant", () => {
    render(
      <HelpLink topic="inbox/scope-density-toggles" label="Which toggle is which?" />,
    );
    expect(
      screen.getByRole("button", { name: /Which toggle is which/i }),
    ).toBeInTheDocument();
  });

  it("honours a custom ariaLabel on the icon variant", () => {
    render(
      <HelpLink
        topic="apex/link-evidence"
        variant="icon"
        ariaLabel="About evidence linkage"
      />,
    );
    expect(
      screen.getByRole("button", { name: /About evidence linkage/i }),
    ).toBeInTheDocument();
  });

  describe("popover variant", () => {
    it("opens an inline popover with title + summary (does NOT dispatch the drawer)", () => {
      render(
        <HelpLink topic="inbox/create-decision-manually" variant="popover" />,
      );
      // Drawer not opened by the popover open itself.
      expect(useHelpStore.getState().open).toBe(false);
      fireEvent.click(screen.getByRole("button"));
      // Article title surfaces inside the popover.
      expect(
        screen.getByText(/Creating a decision record manually/i),
      ).toBeInTheDocument();
      // Drawer still not opened — popover is the whole interaction.
      expect(useHelpStore.getState().open).toBe(false);
    });

    it("'View full article' calls onLaunchFullArticle AND dispatches the drawer", () => {
      const onLaunch = vi.fn();
      render(
        <HelpLink
          topic="inbox/create-decision-manually"
          variant="popover"
          onLaunchFullArticle={onLaunch}
        />,
      );
      fireEvent.click(screen.getByRole("button"));
      fireEvent.click(screen.getByRole("button", { name: /View full article/i }));
      expect(onLaunch).toHaveBeenCalledTimes(1);
      expect(useHelpStore.getState().open).toBe(true);
      expect(useHelpStore.getState().articleId).toBe(
        "inbox/create-decision-manually",
      );
    });
  });
});
