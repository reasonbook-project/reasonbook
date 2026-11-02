// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CurrentUser } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";
import { buildFetchStub, renderWithQuery } from "@/test/helpers";

import { ApexCyclesPage } from "./apexCycles";

const SARAH: CurrentUser = {
  id: "sarah-1",
  username: "sarah.mitchell",
  name: "Sarah Mitchell",
  email: "sarah@example.com",
  title: "CEO",
  role: "admin",
  tenant_id: "us-federal",
  tenant_name: "Riverdale Community Credit Union",
  tier: "federal" as const,
  participant_org_id: null,
  agency_id: "agency-x",
  agency: { id: "agency-x", slug: "x", name: "X", short_name: "X", depth: 0 },
  agency_chain: [],
  oversight_capabilities: null,
};

const JAMIE: CurrentUser = { ...SARAH, role: "member" };

const CYCLES = {
  items: [
    {
      id: "cycle-active",
      tenant_id: "us-federal",
      name: "Q2 2026 Board Cycle",
      cycle_type: "quarterly",
      committee: null,
      cycle_start: "2026-04-01",
      cycle_end: "2026-06-30",
      status: "active",
      meeting_date: "2026-06-15",
      notes: null,
      created_at: "2026-04-01T00:00:00Z",
      created_by: "sarah-1",
      decision_count: 3,
    },
    {
      id: "cycle-concluded",
      tenant_id: "us-federal",
      name: "Q1 2026 Board Cycle",
      cycle_type: "quarterly",
      committee: null,
      cycle_start: "2026-01-01",
      cycle_end: "2026-03-31",
      status: "concluded",
      meeting_date: "2026-03-15",
      notes: "Mid-cycle CCAR",
      created_at: "2026-01-01T00:00:00Z",
      created_by: "sarah-1",
      decision_count: 5,
    },
  ],
};

describe("ApexCyclesPage", () => {
  beforeEach(() => {
    useAuthStore.setState({ status: "authenticated", user: SARAH });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    useAuthStore.setState({ status: "unknown", user: null });
  });

  it("renders cycles grouped by status with download links", async () => {
    const { fetchMock } = buildFetchStub([
      { url: "/api/oversight/cycles", body: CYCLES },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<ApexCyclesPage />);

    expect(await screen.findByText("Q2 2026 Board Cycle")).toBeInTheDocument();
    expect(screen.getByText("Q1 2026 Board Cycle")).toBeInTheDocument();
    // Group headers
    expect(screen.getByText(/^Active · 1$/)).toBeInTheDocument();
    expect(screen.getByText(/^Concluded · 1$/)).toBeInTheDocument();
    // Decision count
    expect(
      screen.getByText(/3 oversight decisions tied to this cycle/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/5 oversight decisions tied to this cycle/i),
    ).toBeInTheDocument();
    // Concluded cycle gets the committee-ready label; active gets the draft label
    const downloadLinks = screen.getAllByRole("link") as HTMLAnchorElement[];
    const concluded = downloadLinks.find((a) => a.textContent === "Download dossier");
    const draft = downloadLinks.find((a) => a.textContent === "Download draft");
    expect(concluded?.getAttribute("href")).toBe(
      "/api/oversight/cycles/cycle-concluded/dossier",
    );
    expect(draft?.getAttribute("href")).toBe(
      "/api/oversight/cycles/cycle-active/dossier",
    );
  });

  it("renders cycles for any authenticated user — oversight is ungated", async () => {
    useAuthStore.setState({ status: "authenticated", user: JAMIE });
    const { fetchMock } = buildFetchStub([
      { url: "/api/oversight/cycles", body: CYCLES },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<ApexCyclesPage />);

    expect(await screen.findByText("Q2 2026 Board Cycle")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalled();
  });

  it("renders the empty-state copy when the tenant has apex but no cycles", async () => {
    const { fetchMock } = buildFetchStub([
      { url: "/api/oversight/cycles", body: { items: [] } },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<ApexCyclesPage />);

    await waitFor(() =>
      expect(screen.getByText(/No oversight cycles yet/i)).toBeInTheDocument(),
    );
  });
});
