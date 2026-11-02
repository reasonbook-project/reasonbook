// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Regression tests for the governance API client.
 *
 * The first version of these endpoints in Prompts 1/3/5 wrapped each
 * call site's body in ``JSON.stringify(...)`` before passing it to
 * ``apiFetch``. ``apiFetch`` itself then ran ``JSON.stringify`` on the
 * already-stringified body, producing a JSON-encoded string on the
 * wire (e.g., ``'"{\\"facet_id\\":...}"'``). Flask parsed that string
 * as a string, the endpoint called ``.get()`` on a string, and every
 * POST/PATCH that landed against a deployed instance 500'd with
 * ``AttributeError: 'str' object has no attribute 'get'``.
 *
 * Existing component + backend tests didn't catch this because they
 * either:
 *
 *   * Bypass ``apiFetch`` (component tests mock the API module directly)
 *   * Send raw JSON via Flask's test client (backend tests)
 *
 * These tests sit at the seam between the two — they intercept
 * ``global.fetch`` and assert the resulting body is a *single*-encoded
 * JSON object whose top-level type is an object, not a string.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createInitiative,
  postRetarget,
  previewComposite,
  updateGovernanceSettings,
} from "./governance";

import type { CreateInitiativeBody } from "./governance";

type FetchSpy = ReturnType<typeof vi.fn>;

function installFetchSpy(): FetchSpy {
  const spy = vi.fn().mockResolvedValue(
    new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  globalThis.fetch = spy as unknown as typeof globalThis.fetch;
  return spy;
}

function lastRequestBody(spy: FetchSpy): unknown {
  const init = spy.mock.calls.at(-1)?.[1] as RequestInit | undefined;
  if (!init?.body) return undefined;
  // Body on the wire should be a single-encoded JSON object. The
  // failure mode this guards: ``JSON.parse(init.body)`` returning a
  // *string* rather than an object means the call site double-encoded.
  return JSON.parse(init.body as string);
}

const SAMPLE_INITIATIVE_BODY: CreateInitiativeBody = {
  facet_id: "ownership",
  current_level: 2,
  target_level: 3,
  started_quarter: "2026-Q3",
  target_completion_quarter: "2027-Q2",
  status: "in_progress",
  milestones: [],
  owner_user_id: "00000000-0000-0000-0000-000000000001",
  source_assessment_id: null,
};

describe("governance API client — body encoding", () => {
  let fetchSpy: FetchSpy;

  beforeEach(() => {
    fetchSpy = installFetchSpy();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("createInitiative sends a JSON object body, not a JSON-encoded string", async () => {
    await createInitiative(SAMPLE_INITIATIVE_BODY);
    const parsed = lastRequestBody(fetchSpy);
    expect(typeof parsed).toBe("object");
    expect(parsed).not.toBeNull();
    expect((parsed as { facet_id: string }).facet_id).toBe("ownership");
  });

  it("previewComposite sends a JSON object body, not a JSON-encoded string", async () => {
    await previewComposite({ ownership: 2, timeliness: 3 });
    const parsed = lastRequestBody(fetchSpy);
    expect(typeof parsed).toBe("object");
    expect((parsed as { facet_placements: Record<string, number> }).facet_placements)
      .toEqual({ ownership: 2, timeliness: 3 });
  });

  it("postRetarget sends a JSON object body, not a JSON-encoded string", async () => {
    await postRetarget("init-1", "proposal-1", "confirm");
    const parsed = lastRequestBody(fetchSpy);
    expect(typeof parsed).toBe("object");
    expect(parsed).toEqual({
      proposal_id: "proposal-1",
      action: "confirm",
    });
  });

  it("updateGovernanceSettings sends a JSON object body, not a JSON-encoded string", async () => {
    await updateGovernanceSettings({ trigger_stuck: false });
    const parsed = lastRequestBody(fetchSpy);
    expect(typeof parsed).toBe("object");
    expect(parsed).toEqual({ trigger_stuck: false });
  });
});
