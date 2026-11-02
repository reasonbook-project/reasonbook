// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AttachmentsBlock } from "./AttachmentsBlock";
import { buildFetchStub, renderWithQuery } from "@/test/helpers";

const ATTACHMENTS = {
  items: [
    {
      id: "att-signal",
      decision_id: "dec-1",
      stage: "signal",
      filename: "signal-screenshot.png",
      content_type: "image/png",
      size_bytes: 12345,
      storage_backend: "local",
      uploaded_by: "user-1",
      uploaded_at: "2026-04-30T12:00:00Z",
      description: null,
      superseded_at: null,
    },
    {
      id: "att-evidence",
      decision_id: "dec-1",
      stage: "evidence",
      filename: "rationale.pdf",
      content_type: "application/pdf",
      size_bytes: 99000,
      storage_backend: "local",
      uploaded_by: "user-1",
      uploaded_at: "2026-04-30T13:00:00Z",
      description: null,
      superseded_at: null,
    },
    {
      id: "att-stale",
      decision_id: "dec-1",
      stage: "signal",
      filename: "old-version.png",
      content_type: "image/png",
      size_bytes: 1000,
      storage_backend: "local",
      uploaded_by: "user-1",
      uploaded_at: "2026-04-29T08:00:00Z",
      description: null,
      superseded_at: "2026-04-30T11:00:00Z",
    },
  ],
};

describe("AttachmentsBlock", () => {
  beforeEach(() => {
    // No-op: each test installs its own stub.
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("filters attachments to the current stage and excludes superseded rows", async () => {
    const { fetchMock } = buildFetchStub([
      { url: "/api/decisions/dec-1/attachments", body: ATTACHMENTS },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<AttachmentsBlock decisionId="dec-1" stage="signal" />);

    await waitFor(() => {
      expect(screen.getByText("signal-screenshot.png")).toBeInTheDocument();
    });
    // evidence-stage row belongs to a different stage.
    expect(screen.queryByText("rationale.pdf")).not.toBeInTheDocument();
    // superseded row is filtered even though it matches the stage.
    expect(screen.queryByText("old-version.png")).not.toBeInTheDocument();
  });

  it("posts a multipart upload when files are picked", async () => {
    const created = {
      id: "att-new",
      decision_id: "dec-1",
      stage: "signal",
      filename: "new.txt",
      content_type: "text/plain",
      size_bytes: 5,
      storage_backend: "local",
      uploaded_by: "user-1",
      uploaded_at: "2026-04-30T14:00:00Z",
      description: null,
      superseded_at: null,
    };
    const { fetchMock } = buildFetchStub([
      { url: "/api/decisions/dec-1/attachments", body: { items: [] } },
      {
        url: "/api/decisions/dec-1/attachments",
        method: "POST",
        status: 201,
        body: created,
      },
      // Refetch after invalidation.
      { url: "/api/decisions/dec-1/attachments", body: { items: [created] } },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<AttachmentsBlock decisionId="dec-1" stage="signal" />);

    await waitFor(() => screen.getByText(/No files yet/i));

    const file = new File(["hello"], "new.txt", { type: "text/plain" });
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    expect(input).toBeTruthy();
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(
        (c) =>
          c[0] === "/api/decisions/dec-1/attachments" &&
          (c[1] as RequestInit | undefined)?.method === "POST",
      );
      expect(postCall).toBeDefined();
      // FormData body — the contract is that fetch sees no JSON body.
      const init = postCall![1] as RequestInit;
      expect(init.body).toBeInstanceOf(FormData);
      const fd = init.body as FormData;
      expect(fd.get("stage")).toBe("signal");
      expect(fd.get("file")).toBeInstanceOf(File);
    });
  });
});
