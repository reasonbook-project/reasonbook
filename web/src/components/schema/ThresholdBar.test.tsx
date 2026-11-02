// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ThresholdBar } from "./ThresholdBar";

describe("ThresholdBar", () => {
  it("renders one labeled stop per defined threshold", () => {
    render(
      <ThresholdBar
        thresholds={{ critical_low: 80, warning_low: 90, target: 95, stretch: 99 }}
        direction="higher_is_better"
        unit="percent"
        format="{value:.1f}%"
        mode="read"
      />,
    );
    expect(screen.getByText("Crit low")).toBeInTheDocument();
    expect(screen.getByText("Warn low")).toBeInTheDocument();
    expect(screen.getByText("Target")).toBeInTheDocument();
    expect(screen.getByText("Stretch")).toBeInTheDocument();
    expect(screen.getByText(/^80\.0%$/)).toBeInTheDocument();
    expect(screen.getByText(/^99\.0%$/)).toBeInTheDocument();
  });

  it("falls back gracefully when no thresholds defined", () => {
    render(
      <ThresholdBar thresholds={{}} direction="neutral" mode="read" />,
    );
    expect(screen.getByText(/no thresholds configured/i)).toBeInTheDocument();
  });

  it("read mode does not render numeric input fields", () => {
    render(
      <ThresholdBar
        thresholds={{ target: 50 }}
        direction="higher_is_better"
        mode="read"
      />,
    );
    expect(screen.queryAllByRole("spinbutton")).toHaveLength(0);
  });

  it("edit mode renders one input per defined stop and fires onChange", () => {
    const onChange = vi.fn();
    render(
      <ThresholdBar
        thresholds={{ warning_low: 90, target: 95, stretch: 99 }}
        direction="higher_is_better"
        mode="edit"
        onChange={onChange}
      />,
    );
    const inputs = screen.getAllByRole("spinbutton");
    expect(inputs).toHaveLength(3);
    fireEvent.change(inputs[0], { target: { value: "92" } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ warning_low: 92 }),
    );
  });

  it("edit mode shows reset affordance only when current diverges from default", () => {
    const onReset = vi.fn();
    const { rerender } = render(
      <ThresholdBar
        thresholds={{ warning_low: 90, target: 95, stretch: 99 }}
        defaultThresholds={{ warning_low: 90, target: 95, stretch: 99 }}
        direction="higher_is_better"
        mode="edit"
        onChange={() => {}}
        onReset={onReset}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /reset to default/i }),
    ).not.toBeInTheDocument();

    // Override one stop — reset should appear.
    rerender(
      <ThresholdBar
        thresholds={{ warning_low: 92, target: 95, stretch: 99 }}
        defaultThresholds={{ warning_low: 90, target: 95, stretch: 99 }}
        direction="higher_is_better"
        mode="edit"
        onChange={() => {}}
        onReset={onReset}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /reset to default/i }),
    );
    expect(onReset).toHaveBeenCalled();
  });

  it("aria-label reflects the metric direction", () => {
    const { rerender } = render(
      <ThresholdBar
        thresholds={{ target: 50 }}
        direction="higher_is_better"
        mode="read"
      />,
    );
    expect(
      screen.getByRole("img", { name: /higher is better/i }),
    ).toBeInTheDocument();

    rerender(
      <ThresholdBar
        thresholds={{ target: 50 }}
        direction="lower_is_better"
        mode="read"
      />,
    );
    expect(
      screen.getByRole("img", { name: /lower is better/i }),
    ).toBeInTheDocument();
  });
});
