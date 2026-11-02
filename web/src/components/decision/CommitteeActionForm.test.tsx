// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { buildFetchStub, renderWithQuery } from "@/test/helpers";

import { CommitteeActionForm } from "./CommitteeActionForm";

describe("CommitteeActionForm", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the three primary board action choices", () => {
    renderWithQuery(<CommitteeActionForm decisionId="apex-1" />);
    expect(screen.getByRole("button", { name: /^Ratify\b/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Note\b/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Defer to next cycle/i }),
    ).toBeInTheDocument();
  });

  it("disables submit until an action is selected", () => {
    renderWithQuery(<CommitteeActionForm decisionId="apex-1" />);
    const submit = screen.getByRole("button", { name: /Record action/i });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /^Ratify\b/i }));
    expect(submit).not.toBeDisabled();
  });

  it("posts the selected action with the optional rationale note", async () => {
    const { fetchMock } = buildFetchStub([
      {
        url: "/api/oversight/decisions/apex-1/board-action",
        method: "POST",
        status: 200,
        body: { ok: true, action: "ratified_by_board" },
      },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<CommitteeActionForm decisionId="apex-1" />);

    fireEvent.click(screen.getByRole("button", { name: /^Ratify\b/i }));
    fireEvent.change(screen.getByLabelText(/Rationale/i), {
      target: { value: "Reviewed evidence; ratified." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Record action/i }));

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(
        (c) =>
          c[0] === "/api/oversight/decisions/apex-1/board-action" &&
          (c[1] as RequestInit | undefined)?.method === "POST",
      );
      expect(postCall).toBeDefined();
      const init = postCall![1] as RequestInit;
      const body = JSON.parse(init.body as string);
      expect(body).toEqual({
        action: "ratified_by_board",
        note: "Reviewed evidence; ratified.",
      });
    });
  });

  it("surfaces a 403 inline as authority error", async () => {
    const { fetchMock } = buildFetchStub([
      {
        url: "/api/oversight/decisions/apex-1/board-action",
        method: "POST",
        status: 403,
        body: { error: "user cannot record board action" },
      },
    ]);
    vi.stubGlobal("fetch", fetchMock);

    renderWithQuery(<CommitteeActionForm decisionId="apex-1" />);

    fireEvent.click(screen.getByRole("button", { name: /^Ratify\b/i }));
    fireEvent.click(screen.getByRole("button", { name: /Record action/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        /don't have authority/i,
      );
    });
  });
});
