// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DecisionRow, type RowSeverity } from "./DecisionRow";

function renderRow(severity?: RowSeverity) {
  render(
    <DecisionRow
      status="critical"
      statusLabel="Due today"
      title="Possible structuring on MEM-234"
      body="02 Regulatory compliance · cluster of $9,800 cash deposits"
      decisionId="DG-2026-04-2118"
      severity={severity}
      isLast
    />,
  );
}

describe("DecisionRow", () => {
  it("omits the severity stripe when severity is not provided", () => {
    renderRow();
    expect(screen.queryByTestId("severity-stripe")).toBeNull();
  });

  it.each([
    ["low", "bg-gray-300"],
    ["medium", "bg-amber-300"],
    ["high", "bg-orange-500"],
    ["critical", "bg-red-600"],
  ] as const)(
    "renders the %s severity stripe with the %s class",
    (severity, expectedClass) => {
      renderRow(severity);
      const stripe = screen.getByTestId("severity-stripe");
      expect(stripe.className).toContain(expectedClass);
      expect(stripe.className).toContain("w-[4px]");
    },
  );

  it("renders the decision ID demoted (smaller + muted-foreground)", () => {
    renderRow("medium");
    const id = screen.getByText("DG-2026-04-2118");
    expect(id.className).toContain("text-[10px]");
    expect(id.className).toContain("text-muted-foreground");
    expect(id.className).toContain("font-normal");
  });
});
