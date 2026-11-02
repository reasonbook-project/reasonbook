// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  DashboardApex,
  DashboardApexOpenDecision,
  DashboardRecentOutcome,
} from "@/api/dashboard";

import type { DashboardWorkflowSummary } from "@/api/dashboard";

import {
  ApexDomainBreakdown,
  buildAtRiskBreakdown,
  CycleOpenDecisions,
  RecentOutcomes,
  Sparkline,
  sortWorkflowsByAtRisk,
} from "./dashboard";

describe("Sparkline", () => {
  it("renders an SVG path with N-1 line segments for N points", () => {
    const points = [
      { week_starting: "2026-04-06", opened_count: 0 },
      { week_starting: "2026-04-13", opened_count: 2 },
      { week_starting: "2026-04-20", opened_count: 1 },
      { week_starting: "2026-04-27", opened_count: 4 },
    ];
    const { container } = render(<Sparkline points={points} color="#3162AA" />);
    const path = container.querySelector("path");
    expect(path).not.toBeNull();
    const d = path!.getAttribute("d") ?? "";
    // One M + three Ls for four points.
    expect((d.match(/M/g) ?? []).length).toBe(1);
    expect((d.match(/L/g) ?? []).length).toBe(3);
    // The latest-week count surfaces as a caption.
    expect(screen.getByText(/4 this wk/)).toBeInTheDocument();
  });

  it("avoids divide-by-zero when every week is zero (max clamps to 1)", () => {
    const points = [
      { week_starting: "2026-04-06", opened_count: 0 },
      { week_starting: "2026-04-13", opened_count: 0 },
    ];
    const { container } = render(<Sparkline points={points} color={null} />);
    const path = container.querySelector("path");
    expect(path?.getAttribute("d")).not.toContain("NaN");
  });
});

describe("sortWorkflowsByAtRisk", () => {
  function row(
    workflow_id: string,
    at_risk_count: number,
    open_count: number,
  ): DashboardWorkflowSummary {
    return {
      workflow_id,
      workflow_name: workflow_id,
      color: null,
      open_count,
      decided_count: 0,
      at_risk_count,
      trend: [],
    };
  }

  it("orders by at_risk DESC, open DESC, then original tiebreak", () => {
    const input = [
      row("a", 0, 5), //                 → 5th (no at-risk, mid open)
      row("b", 12, 3), //                → 1st (highest at-risk)
      row("c", 1, 10), //                → 3rd (1 at-risk, larger open)
      row("d", 1, 4), //                 → 4th (1 at-risk, smaller open)
      row("e", 0, 5), //                 → 6th (tied with a → original order wins)
      row("f", 1, 10), //                → 2nd? no — same at-risk + open as c, original order wins → 4th vs c=3rd
    ];
    const sorted = sortWorkflowsByAtRisk(input).map((w) => w.workflow_id);
    expect(sorted).toEqual(["b", "c", "f", "d", "a", "e"]);
  });

  it("does not mutate the input array", () => {
    const input = [row("a", 0, 1), row("b", 5, 1)];
    const before = input.map((w) => w.workflow_id);
    sortWorkflowsByAtRisk(input);
    expect(input.map((w) => w.workflow_id)).toEqual(before);
  });
});

// dgiScoreColor removed alongside the v1.0 dashboard score card —
// the v2.0 GovernanceCard reads from the assessment composite via
// useCurrentAssessment and doesn't need score-band coloring.

describe("ApexDomainBreakdown", () => {
  const domains: DashboardApex["open_by_domain"] = [
    {
      domain_id: "capital_and_balance_sheet",
      name: "Capital & Balance Sheet",
      primary_owner_role: "cfo",
      open_count: 0,
    },
    {
      domain_id: "risk_appetite",
      name: "Risk Appetite",
      primary_owner_role: "cro",
      open_count: 2,
    },
  ];

  it("renders only domains with open_count > 0 by default", () => {
    render(<ApexDomainBreakdown domains={domains} />);
    expect(screen.getByText("Risk Appetite")).toBeInTheDocument();
    expect(screen.queryByText("Capital & Balance Sheet")).toBeNull();
  });

  it("expands to all domains when 'Show all' is clicked", () => {
    render(<ApexDomainBreakdown domains={domains} />);
    fireEvent.click(screen.getByRole("button", { name: /Show all 2 domains/i }));
    expect(screen.getByText("Capital & Balance Sheet")).toBeInTheDocument();
    expect(screen.getByText("Risk Appetite")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Show fewer/i })).toBeInTheDocument();
  });

  it("omits the toggle when there are no zero-count domains to hide", () => {
    const allActive = domains.map((d) => ({ ...d, open_count: 3 }));
    render(<ApexDomainBreakdown domains={allActive} />);
    expect(screen.queryByRole("button", { name: /Show all/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Show fewer/i })).toBeNull();
  });

  it("falls back to a clear empty-state when nothing is open", () => {
    const allZero = domains.map((d) => ({ ...d, open_count: 0 }));
    render(<ApexDomainBreakdown domains={allZero} />);
    expect(screen.getByText("No open oversight decisions.")).toBeInTheDocument();
  });
});

describe("RecentOutcomes", () => {
  const item: DashboardRecentOutcome = {
    decision_id: "dec-1",
    decision_number: "DG-2026-04-2118",
    title: "SAR filed for member 234",
    workflow_id: "01-regulatory-compliance",
    workflow_name: "Regulatory compliance",
    workflow_color: "#e11d48",
    outcome_recorded_at: new Date(Date.now() - 1000 * 60 * 60 * 24 * 2).toISOString(),
  };

  it("renders one row per outcome and fires onSelect with the row", () => {
    const onSelect = vi.fn();
    render(<RecentOutcomes items={[item]} onSelect={onSelect} />);
    expect(screen.getByText("SAR filed for member 234")).toBeInTheDocument();
    expect(screen.getByText("DG-2026-04-2118")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button"));
    expect(onSelect).toHaveBeenCalledWith(item);
  });

  it("truncates to 5 rows with a 'Show N more' toggle when over the limit", () => {
    const items = Array.from({ length: 8 }, (_, i) => ({
      ...item,
      decision_id: `dec-${i}`,
      decision_number: `DG-2026-04-${1000 + i}`,
      title: `Outcome ${i}`,
    }));
    render(<RecentOutcomes items={items} onSelect={vi.fn()} />);
    // Default render: first 5 visible, last 3 hidden
    expect(screen.getByText("Outcome 0")).toBeInTheDocument();
    expect(screen.getByText("Outcome 4")).toBeInTheDocument();
    expect(screen.queryByText("Outcome 5")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Show 3 more/ }));
    expect(screen.getByText("Outcome 5")).toBeInTheDocument();
    expect(screen.getByText("Outcome 7")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Show less/ })).toBeInTheDocument();
  });

  it("omits the toggle when there are 5 or fewer rows", () => {
    const items = Array.from({ length: 3 }, (_, i) => ({
      ...item,
      decision_id: `dec-${i}`,
      decision_number: `DG-2026-04-${1000 + i}`,
    }));
    render(<RecentOutcomes items={items} onSelect={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Show \d+ more/ })).toBeNull();
  });
});

describe("CycleOpenDecisions", () => {
  const sample: DashboardApexOpenDecision[] = [
    {
      decision_id: "apx-1",
      decision_number: "APX-2026-Q2-001",
      title: "Annual risk appetite framework revision",
      decision_type: "risk_appetite_revision",
      owner_name: "Marcus Webb",
    },
    {
      decision_id: "apx-2",
      decision_number: "APX-2026-Q2-002",
      title: "Tighten unsecured lending tolerance limit",
      decision_type: "risk_tolerance_limit_change",
      owner_name: "Marcus Webb",
    },
  ];

  it("renders one row per in-flight decision with title and owner", () => {
    render(
      <CycleOpenDecisions
        decisions={sample}
        moreCount={0}
        onSelect={vi.fn()}
        onShowAll={vi.fn()}
      />,
    );
    expect(
      screen.getByText("Annual risk appetite framework revision"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Tighten unsecured lending tolerance limit"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Marcus Webb").length).toBe(2);
    // No "+ N more" link when moreCount=0.
    expect(screen.queryByRole("button", { name: /more in this cycle/ })).toBeNull();
  });

  it("clicking a decision row fires onSelect with the decision id", () => {
    const onSelect = vi.fn();
    render(
      <CycleOpenDecisions
        decisions={sample}
        moreCount={0}
        onSelect={onSelect}
        onShowAll={vi.fn()}
      />,
    );
    fireEvent.click(
      screen.getByText("Annual risk appetite framework revision"),
    );
    expect(onSelect).toHaveBeenCalledWith("apx-1");
  });

  it("renders a '+ N more' link when moreCount > 0 and fires onShowAll", () => {
    const onShowAll = vi.fn();
    render(
      <CycleOpenDecisions
        decisions={sample}
        moreCount={3}
        onSelect={vi.fn()}
        onShowAll={onShowAll}
      />,
    );
    const more = screen.getByRole("button", { name: /\+ 3 more in this cycle/ });
    fireEvent.click(more);
    expect(onShowAll).toHaveBeenCalledTimes(1);
  });
});

/**
 * Phase 5 verification 5.8 — defensive defaults for the at-risk
 * breakdown shape. Backend ships an array of non-zero entries; TopRail
 * expects a {credit, compliance, ops} object. The conversion must not
 * crash, render NaN, or drop the zero-default floor for missing
 * categories.
 */
describe("buildAtRiskBreakdown", () => {
  it("returns all-zero defaults for null input", () => {
    expect(buildAtRiskBreakdown(null)).toEqual({
      credit: 0,
      compliance: 0,
      ops: 0,
    });
  });

  it("returns all-zero defaults for undefined input", () => {
    expect(buildAtRiskBreakdown(undefined)).toEqual({
      credit: 0,
      compliance: 0,
      ops: 0,
    });
  });

  it("returns all-zero defaults for an empty array", () => {
    expect(buildAtRiskBreakdown([])).toEqual({
      credit: 0,
      compliance: 0,
      ops: 0,
    });
  });

  it("overlays a single category, leaves the rest at zero", () => {
    expect(buildAtRiskBreakdown([{ label: "credit", count: 5 }])).toEqual({
      credit: 5,
      compliance: 0,
      ops: 0,
    });
  });

  it("overlays all three categories when all are present", () => {
    expect(
      buildAtRiskBreakdown([
        { label: "compliance", count: 10 },
        { label: "ops", count: 3 },
        { label: "credit", count: 2 },
      ]),
    ).toEqual({ credit: 2, compliance: 10, ops: 3 });
  });

  it("preserves unknown category labels on the object without crashing", () => {
    // Future backend buckets (e.g. 'vendor') land on the object but
    // aren't read by the typed TopRail consumer. No crash, no NaN.
    const result = buildAtRiskBreakdown([
      { label: "credit", count: 5 },
      { label: "vendor", count: 2 },
    ]);
    expect(result.credit).toBe(5);
    expect(result.compliance).toBe(0);
    expect(result.ops).toBe(0);
    // Forensic: unknown key didn't blow away the defaults.
    expect(Object.keys(result)).toEqual(
      expect.arrayContaining(["credit", "compliance", "ops"]),
    );
  });
});
