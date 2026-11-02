// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EvidenceSection } from "./EvidenceSection";
import { buildFetchStub, renderWithQuery } from "@/test/helpers";

const APEX_ID = "apex-001";

const WORKFLOWS = {
  workflows: [
    { id: "01-regulatory-compliance", name: "Regulatory compliance", color: "#e11d48" },
    { id: "01-regulatory-compliance", name: "Regulatory Compliance", color: "#0ea5e9" },
  ],
};

const EVIDENCE = {
  items: [
    {
      id: "link-1",
      oversight_decision_id: APEX_ID,
      operational_decision_id: "op-1",
      evidence_role: "primary_evidence",
      link_rationale: "SAR pattern justifies risk appetite tightening.",
      linked_at: "2026-04-15T10:00:00Z",
      linked_by: "user-cro",
      superseded_at: null,
      superseded_by_link_id: null,
      operational: {
        id: "op-1",
        decision_number: "DG-2026-04-0042",
        title: "File SAR for $42K structuring pattern",
        workflow_id: "01-regulatory-compliance",
        status: "decided",
        decided_at: "2026-04-10T00:00:00Z",
      },
    },
    {
      id: "link-2",
      oversight_decision_id: APEX_ID,
      operational_decision_id: "op-2",
      evidence_role: "supporting_evidence",
      link_rationale: null,
      linked_at: "2026-04-15T10:05:00Z",
      linked_by: "user-cro",
      superseded_at: null,
      superseded_by_link_id: null,
      operational: {
        id: "op-2",
        decision_number: "DG-2026-04-0099",
        title: "Adjust grant-integrity monitoring thresholds",
        workflow_id: "01-regulatory-compliance",
        status: "decided",
        decided_at: "2026-04-12T00:00:00Z",
      },
    },
  ],
};

function installFetch(routes: Parameters<typeof buildFetchStub>[0]) {
  const { fetchMock } = buildFetchStub(routes);
  vi.stubGlobal("fetch", fetchMock);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EvidenceSection", () => {
  it("renders evidence grouped by role with workflow chips", async () => {
    installFetch([
      { url: `/api/oversight/decisions/${APEX_ID}/evidence`, body: EVIDENCE },
      { url: "/api/workflows", body: WORKFLOWS },
    ]);

    renderWithQuery(<EvidenceSection oversightDecisionId={APEX_ID} />);

    await waitFor(() => {
      expect(screen.getByText(/2 linked/)).toBeInTheDocument();
    });

    // Both role headings render.
    expect(screen.getByText("Primary")).toBeInTheDocument();
    expect(screen.getByText("Supporting")).toBeInTheDocument();

    // Operational decision titles + numbers visible.
    expect(
      screen.getByText("File SAR for $42K structuring pattern"),
    ).toBeInTheDocument();
    expect(screen.getByText("DG-2026-04-0042")).toBeInTheDocument();

    // Rationale renders only when present.
    expect(
      screen.getByText(/SAR pattern justifies risk appetite/),
    ).toBeInTheDocument();
  });

  it("shows the empty hint when no evidence is linked", async () => {
    installFetch([
      { url: `/api/oversight/decisions/${APEX_ID}/evidence`, body: { items: [] } },
      { url: "/api/workflows", body: WORKFLOWS },
    ]);

    renderWithQuery(<EvidenceSection oversightDecisionId={APEX_ID} />);

    await waitFor(() => {
      expect(
        screen.getByText(/No operational evidence linked yet/),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/0 linked/)).toBeInTheDocument();
  });
});
