// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "./client";

describe("apiFetch", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends JSON body and credentials, parses JSON response", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "abc" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const out = await apiFetch<{ id: string }>("/api/x", {
      method: "POST",
      body: { foo: 1 },
    });
    expect(out).toEqual({ id: "abc" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe("include");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ foo: 1 }));
  });

  it("throws ApiError with parsed body on non-2xx", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: "nope" }), { status: 401 }),
    );
    let caught: unknown = null;
    try {
      await apiFetch("/api/y");
    } catch (exc) {
      caught = exc;
    }
    expect(caught).toBeInstanceOf(ApiError);
    const err = caught as ApiError;
    expect(err.status).toBe(401);
    expect(err.body).toEqual({ error: "nope" });
  });

  it("returns null when the response body is empty", async () => {
    fetchMock.mockResolvedValueOnce(new Response("", { status: 200 }));
    const out = await apiFetch("/api/z");
    expect(out).toBeNull();
  });
});
