// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useHelpStore } from "@/stores/help";

import { HelpDrawer } from "./HelpDrawer";

describe("HelpDrawer", () => {
  beforeEach(() => {
    // Open the drawer to the index for each test. Individual tests
    // override via useHelpStore.setState when they need a different
    // entry point.
    useHelpStore.setState({ open: true, articleId: null });
  });

  afterEach(() => {
    // Drawer mounts a Provider/Portal — make sure each test starts clean.
    useHelpStore.setState({ open: false, articleId: null });
    document.body.innerHTML = "";
  });

  it("renders the article index when open and not viewing an article", () => {
    render(<HelpDrawer />);
    expect(screen.getByPlaceholderText(/Search help/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Your first decision/i }),
    ).toBeInTheDocument();
    // All seven current articles present.
    expect(
      screen.getByRole("button", { name: /Claiming a decision/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Finalizing a decision/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Reading your Governance Profile/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /AI Suggestions on the Governance Roadmap/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /Scope and density toggles in the Inbox/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /Linking operational evidence to an apex decision/i,
      }),
    ).toBeInTheDocument();
  });

  it("filters articles by search term across title + body", () => {
    render(<HelpDrawer />);
    const search = screen.getByPlaceholderText(/Search help/i);
    fireEvent.change(search, { target: { value: "SAR" } });
    // "Finalizing a decision" mentions SAR in the body.
    expect(
      screen.getByRole("button", { name: /Finalizing a decision/i }),
    ).toBeInTheDocument();
    // "Reading your Governance Profile" does not mention SAR — should be
    // filtered out.
    expect(
      screen.queryByRole("button", { name: /Reading your Governance Profile/i }),
    ).not.toBeInTheDocument();
  });

  it("renders empty state when no articles match search", () => {
    render(<HelpDrawer />);
    fireEvent.change(screen.getByPlaceholderText(/Search help/i), {
      target: { value: "zzzzzzzzzzz" },
    });
    expect(screen.getByText(/No articles match/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /send feedback/i }),
    ).not.toBeInTheDocument();
  });

  it("opens an article when its index entry is clicked", async () => {
    render(<HelpDrawer />);
    fireEvent.click(
      screen.getByRole("button", { name: /Claiming a decision/i }),
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Back to help index/i }),
      ).toBeInTheDocument();
    });
    // Article header surfaces (rendered as h2 by HelpArticle).
    expect(
      screen.getByRole("heading", { name: /Claiming a decision/i, level: 2 }),
    ).toBeInTheDocument();
  });

  it("opens directly to an article when the store seeds articleId", async () => {
    useHelpStore.setState({ open: true, articleId: "decisions/finalize" });
    render(<HelpDrawer />);
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Finalizing a decision/i, level: 2 }),
      ).toBeInTheDocument();
    });
  });

  it("returns to the index from an article via 'Back to help index'", async () => {
    render(<HelpDrawer />);
    fireEvent.click(
      screen.getByRole("button", { name: /Claiming a decision/i }),
    );
    await waitFor(() => screen.getByRole("button", { name: /Back to help/i }));
    fireEvent.click(screen.getByRole("button", { name: /Back to help/i }));
    expect(screen.getByPlaceholderText(/Search help/i)).toBeInTheDocument();
  });

  it("clears store state when the X button is clicked", () => {
    render(<HelpDrawer />);
    fireEvent.click(screen.getByRole("button", { name: /Close help/i }));
    expect(useHelpStore.getState().open).toBe(false);
    expect(useHelpStore.getState().articleId).toBeNull();
  });
});
