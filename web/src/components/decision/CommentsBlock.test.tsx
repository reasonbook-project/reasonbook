// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CommentsBlock } from "./CommentsBlock";
import { useAuthStore } from "@/stores/auth";
import { buildFetchStub, renderWithQuery } from "@/test/helpers";

const ME = {
  id: "user-self",
  username: "jamie",
  name: "Jamie Kim",
  email: "jamie@example.com",
  title: null,
  role: "member" as const,
  tenant_id: "us-federal",
  tenant_name: "Riverdale CU",
  tier: "federal" as const,
  participant_org_id: null,
  agency_id: "agency-x",
  agency: { id: "agency-x", slug: "x", name: "X", short_name: "X", depth: 0 },
  agency_chain: [],
  oversight_capabilities: null,
};

const COMMENTS = {
  items: [
    {
      id: "ev-1",
      decision_id: "dec-1",
      tenant_id: "us-federal",
      workflow_id: "01-regulatory-compliance",
      user_id: "user-self",
      user_name: "Jamie Kim",
      user_username: "jamie",
      action: "comment",
      old_status: null,
      new_status: null,
      comment: "Reviewing the structuring pattern.",
      metadata: { stage_context: "signal", mentions: [] },
      created_at: "2026-04-30T10:00:00Z",
    },
    {
      id: "ev-2",
      decision_id: "dec-1",
      tenant_id: "us-federal",
      workflow_id: "01-regulatory-compliance",
      user_id: "user-other",
      user_name: "Marcus Webb",
      user_username: "marcus.webb",
      action: "comment",
      old_status: null,
      new_status: null,
      comment: "Off-topic — wrong stage.",
      metadata: { stage_context: "decision", mentions: [] },
      created_at: "2026-04-30T11:00:00Z",
    },
    {
      id: "ev-3",
      decision_id: "dec-1",
      tenant_id: "us-federal",
      workflow_id: "01-regulatory-compliance",
      user_id: "user-other",
      user_name: "Marcus Webb",
      user_username: "marcus.webb",
      action: "comment",
      old_status: null,
      new_status: null,
      comment: "Decision-level discussion thread.",
      metadata: { stage_context: "general", mentions: [] },
      created_at: "2026-04-30T12:00:00Z",
    },
  ],
};

describe("CommentsBlock", () => {
  beforeEach(() => {
    useAuthStore.getState().setUser(ME);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    useAuthStore.getState().reset();
  });

  it("filters comments to the current stage_context", async () => {
    const { fetchMock } = buildFetchStub([
      {
        url: "/api/decisions/dec-1/events?include=comments",
        body: COMMENTS,
      },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<CommentsBlock decisionId="dec-1" stageContext="signal" />);

    await waitFor(() => {
      expect(screen.getByText("Reviewing the structuring pattern.")).toBeInTheDocument();
    });
    // Other contexts are filtered out.
    expect(screen.queryByText("Off-topic — wrong stage.")).not.toBeInTheDocument();
    expect(screen.queryByText("Decision-level discussion thread.")).not.toBeInTheDocument();
  });

  it("renders the general thread when scoped to general", async () => {
    const { fetchMock } = buildFetchStub([
      {
        url: "/api/decisions/dec-1/events?include=comments",
        body: COMMENTS,
      },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<CommentsBlock decisionId="dec-1" stageContext="general" />);

    await waitFor(() => {
      expect(
        screen.getByText("Decision-level discussion thread."),
      ).toBeInTheDocument();
    });
  });

  it("posts a comment under the current stage_context", async () => {
    const newComment = {
      id: "ev-4",
      decision_id: "dec-1",
      tenant_id: "us-federal",
      workflow_id: "01-regulatory-compliance",
      user_id: "user-self",
      user_name: "Jamie Kim",
      user_username: "jamie",
      action: "comment",
      old_status: null,
      new_status: null,
      comment: "Adding a note here.",
      metadata: { stage_context: "general", mentions: [] },
      created_at: "2026-04-30T13:00:00Z",
    };
    const { fetchMock } = buildFetchStub([
      { url: "/api/decisions/dec-1/events?include=comments", body: { items: [] } },
      {
        url: "/api/decisions/dec-1/comments",
        method: "POST",
        status: 201,
        body: newComment,
      },
      // Refetch after mutation invalidates.
      {
        url: "/api/decisions/dec-1/events?include=comments",
        body: { items: [newComment] },
      },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(
      <CommentsBlock decisionId="dec-1" stageContext="general" />,
    );

    await waitFor(() => screen.getByPlaceholderText(/Add a comment/i));
    fireEvent.change(screen.getByPlaceholderText(/Add a comment/i), {
      target: { value: "Adding a note here." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Post comment/i }));

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(
        (c) =>
          c[0] === "/api/decisions/dec-1/comments" &&
          (c[1] as RequestInit | undefined)?.method === "POST",
      );
      expect(postCall).toBeDefined();
      const init = postCall![1] as RequestInit;
      const body = JSON.parse(init.body as string);
      expect(body).toEqual({
        body: "Adding a note here.",
        stage_context: "general",
      });
    });
  });
});
