// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowConfig } from "@/api/workflows";

import { MetricsTab, DecisionTypesTab, AlertsTab } from "./tabs";

function makeCfg(overrides: Partial<WorkflowConfig>): WorkflowConfig {
  return {
    workflow: {
      id: "01-regulatory-compliance",
      name: "Regulatory compliance",
      description: "Grant-integrity workflow",
      icon: null,
      color: null,
      version: "1.0",
      oversight_contributing: true,
    },
    metrics: [],
    decision_types: [],
    authority_levels: [],
    upload: null,
    ...overrides,
  };
}

describe("schema tabs · workflow tag visibility", () => {
  it("MetricsTab omits the workflow tag when only one workflow is in view", () => {
    const cfg = makeCfg({
      metrics: [{ id: "sar_filing_count", name: "SARs filed" }],
    });
    render(<MetricsTab workflows={[cfg]} />);
    expect(screen.getByText("sar_filing_count")).toBeInTheDocument();
    // Workflow display name should not surface as a tag in single-cfg view.
    expect(screen.queryByText("Regulatory compliance")).toBeNull();
  });

  it("MetricsTab renders a workflow tag per item when multiple workflows are in view", () => {
    const bsa = makeCfg({
      metrics: [{ id: "sar_filing_count", name: "SARs filed" }],
    });
    const reg = makeCfg({
      workflow: {
        ...bsa.workflow,
        id: "01-regulatory-compliance",
        name: "Regulatory Compliance",
      },
      metrics: [{ id: "exam_findings_open", name: "Open exam findings" }],
    });
    render(<MetricsTab workflows={[bsa, reg]} />);
    expect(screen.getByText("Regulatory compliance")).toBeInTheDocument();
    expect(screen.getByText("Regulatory Compliance")).toBeInTheDocument();
  });
});

describe("schema tabs · aggregation", () => {
  it("AlertsTab combines alert categories from every workflow in view", () => {
    const bsa = makeCfg({
      alert_categories: [
        { id: "structuring", name: "Structuring", description: null, color: null },
      ],
    });
    const reg = makeCfg({
      workflow: { ...bsa.workflow, id: "01-reg", name: "Reg" },
      alert_categories: [
        { id: "exam_finding", name: "Exam finding", description: null, color: null },
      ],
    });
    render(<AlertsTab workflows={[bsa, reg]} />);
    expect(screen.getByText("structuring")).toBeInTheDocument();
    expect(screen.getByText("exam_finding")).toBeInTheDocument();
  });

  it("DecisionTypesTab is empty-state when no decision types exist across workflows", () => {
    render(<DecisionTypesTab workflows={[makeCfg({})]} />);
    expect(
      screen.getByText("No decision types defined."),
    ).toBeInTheDocument();
  });
});

describe("schema tabs · search filter", () => {
  it("MetricsTab filters by substring across name/id/description/category", () => {
    const cfg = makeCfg({
      metrics: [
        { id: "sar_filing_count", name: "SARs filed" },
        { id: "ctr_filing_count", name: "CTRs filed" },
        { id: "alert_disposition_rate", name: "Alert disposition rate" },
      ],
    });
    render(<MetricsTab workflows={[cfg]} query="sar" />);
    expect(screen.getByText("sar_filing_count")).toBeInTheDocument();
    expect(screen.queryByText("ctr_filing_count")).toBeNull();
    expect(screen.queryByText("alert_disposition_rate")).toBeNull();
  });

  it("MetricsTab shows the no-matches state with a clear-search action", () => {
    const cfg = makeCfg({
      metrics: [{ id: "sar_filing_count", name: "SARs filed" }],
    });
    const onClearSearch = vi.fn();
    render(
      <MetricsTab
        workflows={[cfg]}
        query="zzz_nonexistent"
        onClearSearch={onClearSearch}
      />,
    );
    expect(
      screen.getByText(/No items match/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Clear search/ }));
    expect(onClearSearch).toHaveBeenCalled();
  });

  it("MetricsTab dimension chips populate from items + filter on toggle", () => {
    const cfg = makeCfg({
      metrics: [
        { id: "a", name: "A", category: "oig_referral" } as never,
        { id: "b", name: "B", category: "due_diligence" } as never,
        { id: "c", name: "C", category: "oig_referral" } as never,
      ],
    });
    const onDimsChange = vi.fn();
    render(
      <MetricsTab
        workflows={[cfg]}
        activeDims={["oig_referral"]}
        onDimsChange={onDimsChange}
      />,
    );
    // Active chip rendered with aria-pressed
    const bsaChip = screen.getByRole("button", { name: /OIG_REFERRAL/ });
    expect(bsaChip).toHaveAttribute("aria-pressed", "true");
    // Items B (due_diligence) is filtered out, A and C survive
    expect(screen.getByText("a")).toBeInTheDocument();
    expect(screen.getByText("c")).toBeInTheDocument();
    expect(screen.queryByText("b")).toBeNull();
    // Toggling fires the callback with the filtered set
    fireEvent.click(bsaChip);
    expect(onDimsChange).toHaveBeenCalledWith([]);
  });

  it("AlertsTab filters by query and has no dimension chips (alerts have no sub-category)", () => {
    const cfg = makeCfg({
      alert_categories: [
        {
          id: "structuring",
          name: "Structuring",
          description: null,
          color: null,
        },
        {
          id: "exam_finding",
          name: "Exam finding",
          description: null,
          color: null,
        },
      ],
    });
    render(<AlertsTab workflows={[cfg]} query="struct" />);
    expect(screen.getByText("structuring")).toBeInTheDocument();
    expect(screen.queryByText("exam_finding")).toBeNull();
    // No dimension chips render — the chip row component returns null
    // when `available` is empty.
    expect(screen.queryByRole("button", { name: /Clear all/ })).toBeNull();
  });

  it("Showing-X-of-Y count appears only when the filter is narrowing", () => {
    const cfg = makeCfg({
      metrics: [
        { id: "a", name: "A" },
        { id: "b", name: "B" },
        { id: "c", name: "C" },
      ],
    });
    // Unfiltered — count line should be suppressed
    const { rerender } = render(<MetricsTab workflows={[cfg]} />);
    expect(screen.queryByText(/Showing/)).toBeNull();
    // Filtered — count line surfaces
    rerender(<MetricsTab workflows={[cfg]} query="a" />);
    expect(screen.getByText(/Showing 1 of 3/)).toBeInTheDocument();
  });
});
