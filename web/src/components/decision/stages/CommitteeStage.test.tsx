// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CurrentUser } from "@/api/auth";
import type { Decision } from "@/api/decisions";
import { useAuthStore } from "@/stores/auth";
import { buildFetchStub, renderWithQuery } from "@/test/helpers";

import { CommitteeStage } from "./CommitteeStage";

const WALTER: CurrentUser = {
  id: "walter-1",
  username: "walter.knox",
  name: "Walter Knox",
  email: "walter@example.com",
  title: "Board Chair",
  role: "member",
  tenant_id: "us-federal",
  tenant_name: "Riverdale CU",
  tier: "federal" as const,
  participant_org_id: null,
  agency_id: "agency-x",
  agency: { id: "agency-x", slug: "x", name: "X", short_name: "X", depth: 0 },
  agency_chain: [],
  oversight_capabilities: {
    oversight_role: "board_chair",
    domains_owned: [],
    can_record_committee_action: true,
    is_executive: false,
    is_committee: true,
    level: 4,
  },
};

const PRIYA: CurrentUser = {
  ...WALTER,
  id: "priya-1",
  username: "priya.shah",
  name: "Priya Shah",
  title: "CCO",
  tier: "federal" as const,
  participant_org_id: null,
  agency_id: "agency-x",
  agency: { id: "agency-x", slug: "x", name: "X", short_name: "X", depth: 0 },
  agency_chain: [],
  oversight_capabilities: {
    oversight_role: "cco",
    domains_owned: ["regulatory_posture"],
    can_record_committee_action: false,
    is_executive: true,
    is_committee: false,
    level: 3,
  },
};

const NON_APEX_USER: CurrentUser = {
  ...WALTER,
  id: "jamie-1",
  username: "jamie.kim",
  name: "Jamie Kim",
  title: "Grant integrity officer",
  tier: "federal" as const,
  participant_org_id: null,
  agency_id: "agency-x",
  agency: { id: "agency-x", slug: "x", name: "X", short_name: "X", depth: 0 },
  agency_chain: [],
  oversight_capabilities: null,
};

function buildDecision(overrides: Partial<Decision> = {}): Decision {
  return {
    id: "apex-1",
    decision_number: "DG-2026-Q2-A50",
    tenant_id: "us-federal",
    workflow_id: "10-oversight",
    decision_type: "facet_advancement_review",
    title: "Review Q2·26 floor advancement (L1 → L2)",
    description: null,
    priority: "high",
    severity: "medium",
    status: "in_progress",
    sla_hours: 2160,
    sla_deadline: null,
    sla_status: "on_track",
    signal_captured_at: null,
    signal_source: null,
    signal_summary: null,
    trigger_data: null,
    owner_id: "priya-1",
    created_by: "priya-1",
    assigned_at: null,
    acknowledged_at: null,
    owner_authority_level: 4,
    escalation_path: null,
    decided_at: null,
    selected_option: null,
    alternatives: null,
    evidence_refs: null,
    rationale: null,
    action_started_at: null,
    action_completed_at: null,
    action_artifacts: null,
    outcome_recorded_at: null,
    outcome_text: null,
    outcome_impact: null,
    outcome_metrics: null,
    closed_at: null,
    defer_reason: null,
    defer_reopen_at: null,
    escalated_to: null,
    escalation_reason: null,
    ...overrides,
  } as Decision;
}

const EMPTY_EVENTS = { items: [] };

const ONE_RATIFICATION = {
  items: [
    {
      id: "ev-1",
      decision_id: "apex-1",
      tenant_id: "us-federal",
      workflow_id: "10-oversight",
      user_id: "walter-1",
      user_name: "Walter Knox",
      user_username: "walter.knox",
      action: "ratified_by_board",
      old_status: null,
      new_status: null,
      comment: "Reviewed Q2 evidence; ratified.",
      metadata: null,
      created_at: "2026-04-15T14:00:00Z",
    },
  ],
};

describe("CommitteeStage", () => {
  beforeEach(() => {
    useAuthStore.getState().reset();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    useAuthStore.getState().reset();
  });

  it("renders 'Awaiting committee ratification' + matrix for board personas", async () => {
    useAuthStore.getState().setUser(WALTER);
    const { fetchMock } = buildFetchStub([
      {
        url: "/api/decisions/apex-1/events",
        body: EMPTY_EVENTS,
      },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<CommitteeStage decision={buildDecision()} />);

    await waitFor(() => {
      expect(screen.getByText(/Awaiting committee ratification/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /^Ratify\b/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Defer to next cycle/i }),
    ).toBeInTheDocument();
  });

  it("does not render the matrix for executive (non-board) personas", async () => {
    useAuthStore.getState().setUser(PRIYA);
    const { fetchMock } = buildFetchStub([
      {
        url: "/api/decisions/apex-1/events",
        body: EMPTY_EVENTS,
      },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<CommitteeStage decision={buildDecision()} />);

    await waitFor(() => {
      expect(screen.getByText(/Awaiting committee ratification/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /^Ratify\b/i })).not.toBeInTheDocument();
  });

  it("does not render the matrix for users with no apex grant", async () => {
    useAuthStore.getState().setUser(NON_APEX_USER);
    const { fetchMock } = buildFetchStub([
      {
        url: "/api/decisions/apex-1/events",
        body: EMPTY_EVENTS,
      },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<CommitteeStage decision={buildDecision()} />);

    await waitFor(() => {
      expect(screen.getByText(/Awaiting committee ratification/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /^Ratify\b/i })).not.toBeInTheDocument();
  });

  it("renders the populated state with the board event", async () => {
    useAuthStore.getState().setUser(WALTER);
    const { fetchMock } = buildFetchStub([
      {
        url: "/api/decisions/apex-1/events",
        body: ONE_RATIFICATION,
      },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<CommitteeStage decision={buildDecision()} />);

    await waitFor(() => {
      expect(screen.getByText(/Ratified by board/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Walter Knox/)).toBeInTheDocument();
    expect(
      screen.getByText(/Reviewed Q2 evidence; ratified/i),
    ).toBeInTheDocument();
    // Matrix still available for further actions until closed.
    expect(screen.getByRole("button", { name: /^Ratify\b/i })).toBeInTheDocument();
  });

  it("hides the matrix once the decision is closed", async () => {
    useAuthStore.getState().setUser(WALTER);
    const { fetchMock } = buildFetchStub([
      {
        url: "/api/decisions/apex-1/events",
        body: EMPTY_EVENTS,
      },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<CommitteeStage decision={buildDecision({ status: "closed" })} />);

    await waitFor(() => {
      expect(screen.getByText(/Awaiting committee ratification/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /^Ratify\b/i })).not.toBeInTheDocument();
  });
});
