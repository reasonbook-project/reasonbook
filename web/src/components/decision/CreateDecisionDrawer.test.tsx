// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CreateDecisionDrawer } from "./CreateDecisionDrawer";
import { buildFetchStub, renderWithQuery } from "@/test/helpers";

const navigateMock = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigateMock,
}));

const WORKFLOWS = {
  workflows: [
    {
      id: "01-regulatory-compliance",
      name: "Regulatory compliance",
      description: "",
      icon: null,
      color: "#e11d48",
      version: "1.0",
      oversight_contributing: true,
    },
  ],
};

const CONFIG = {
  workflow: WORKFLOWS.workflows[0],
  metrics: [],
  authority_levels: [],
  decision_types: [
    {
      id: "sar_filing_decision",
      name: "SAR Filing Decision",
      manually_creatable: true,
      authoring_authority_level: "bsa_officer",
      oversight_evidence_eligible: false,
      available_actions: [],
      outcome_metrics: [],
    },
    {
      id: "bsa_aml_alert",
      name: "Program-integrity alert",
      manually_creatable: false,
      authoring_authority_level: null,
      oversight_evidence_eligible: true,
      available_actions: [],
      outcome_metrics: [],
    },
  ],
};

describe("CreateDecisionDrawer", () => {
  beforeEach(() => {
    navigateMock.mockReset();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("filters decision-type options to manually_creatable=true only", async () => {
    const { fetchMock } = buildFetchStub([
      { url: "/api/workflows", body: WORKFLOWS },
      { url: "/api/workflows/01-regulatory-compliance/config", body: CONFIG },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<CreateDecisionDrawer open onClose={() => {}} />);

    // Pick the workflow — wait for the option to load before changing.
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Regulatory compliance" })).toBeInTheDocument();
    });
    fireEvent.change(screen.getByLabelText(/Workflow/i), {
      target: { value: "01-regulatory-compliance" },
    });

    // Wait for the config fetch to settle.
    await waitFor(() => {
      const typeSelect = screen.getByLabelText(/Decision type/i);
      expect(typeSelect).not.toBeDisabled();
    });

    const typeSelect = screen.getByLabelText(/Decision type/i) as HTMLSelectElement;
    const optionLabels = Array.from(typeSelect.options).map((o) => o.textContent);

    expect(optionLabels).toContain("SAR Filing Decision");
    expect(optionLabels).not.toContain("Program-integrity alert");
  });

  it("submits create with the selected workflow and type, then navigates", async () => {
    const createdDecision = {
      id: "dec-uuid",
      workflow_id: "01-regulatory-compliance",
      decision_type: "sar_filing_decision",
    };
    const { fetchMock } = buildFetchStub([
      { url: "/api/workflows", body: WORKFLOWS },
      { url: "/api/workflows/01-regulatory-compliance/config", body: CONFIG },
      { url: "/api/decisions", method: "POST", status: 201, body: createdDecision },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    const onClose = vi.fn();
    renderWithQuery(<CreateDecisionDrawer open onClose={onClose} />);

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Regulatory compliance" })).toBeInTheDocument();
    });
    fireEvent.change(screen.getByLabelText(/Workflow/i), {
      target: { value: "01-regulatory-compliance" },
    });

    await waitFor(() => {
      expect(screen.getByLabelText(/Decision type/i)).not.toBeDisabled();
    });
    fireEvent.change(screen.getByLabelText(/Decision type/i), {
      target: { value: "sar_filing_decision" },
    });
    fireEvent.change(screen.getByLabelText(/Title/i), {
      target: { value: "Structured deposits across linked accounts" },
    });

    fireEvent.click(screen.getByRole("button", { name: /^Add record$/i }));

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith({
        to: "/workflows/$workflowId/decisions/$decisionId",
        params: { workflowId: "01-regulatory-compliance", decisionId: "dec-uuid" },
      });
    });
    expect(onClose).toHaveBeenCalled();

    const postCall = fetchMock.mock.calls.find(
      (c) => c[0] === "/api/decisions" && (c[1] as RequestInit | undefined)?.method === "POST",
    );
    expect(postCall).toBeDefined();
    const sentBody = JSON.parse((postCall![1] as RequestInit).body as string);
    expect(sentBody).toMatchObject({
      workflow_id: "01-regulatory-compliance",
      decision_type: "sar_filing_decision",
      title: "Structured deposits across linked accounts",
    });
  });

  it("surfaces the server's error message on 403", async () => {
    const { fetchMock } = buildFetchStub([
      { url: "/api/workflows", body: WORKFLOWS },
      { url: "/api/workflows/01-regulatory-compliance/config", body: CONFIG },
      {
        url: "/api/decisions",
        method: "POST",
        status: 403,
        body: { error: "user authority below required level" },
      },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<CreateDecisionDrawer open onClose={() => {}} />);

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Regulatory compliance" })).toBeInTheDocument();
    });
    fireEvent.change(screen.getByLabelText(/Workflow/i), {
      target: { value: "01-regulatory-compliance" },
    });
    await waitFor(() => {
      expect(screen.getByLabelText(/Decision type/i)).not.toBeDisabled();
    });
    fireEvent.change(screen.getByLabelText(/Decision type/i), {
      target: { value: "sar_filing_decision" },
    });
    fireEvent.change(screen.getByLabelText(/Title/i), {
      target: { value: "blocked attempt" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Add record$/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/user authority below required level/i),
      ).toBeInTheDocument();
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
