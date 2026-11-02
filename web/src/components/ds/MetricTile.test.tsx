// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MetricTile } from "./MetricTile";

describe("MetricTile", () => {
  it("renders label, value, and caption", () => {
    render(
      <MetricTile label="Signals" value={24} caption="New, unowned" />,
    );
    expect(screen.getByText("Signals")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();
    expect(screen.getByText("New, unowned")).toBeInTheDocument();
  });

  it("invokes onClick when the tile is clicked", () => {
    const onClick = vi.fn();
    render(
      <MetricTile
        label="Decisions"
        value={38}
        caption="Owned, in progress"
        onClick={onClick}
      />,
    );
    fireEvent.click(screen.getByText("Decisions"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("suppresses the trend in the empty state", () => {
    render(
      <MetricTile
        label="Outcomes"
        value={0}
        caption="Nothing recorded"
        state="empty"
        trend={{ direction: "up", delta: "ignored", intent: "warning" }}
      />,
    );
    expect(screen.queryByText(/ignored/)).not.toBeInTheDocument();
  });

  it("renders the trend delta and glyph when provided", () => {
    render(
      <MetricTile
        label="Signals"
        value={24}
        caption="New, unowned"
        trend={{ direction: "up", delta: "12% wk-over-wk", intent: "warning" }}
      />,
    );
    expect(screen.getByText(/12% wk-over-wk/)).toBeInTheDocument();
  });
});
