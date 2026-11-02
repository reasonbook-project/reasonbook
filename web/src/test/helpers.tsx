// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { vi } from "vitest";

/**
 * Test helper that wraps a component in a fresh QueryClient. Each call gets
 * its own client so cache state can't leak between tests.
 *
 * Retry is disabled — without it, mutations that error in tests stall
 * waiting for the default 3-attempt back-off.
 */
export function renderWithQuery(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">,
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { ...render(ui, { wrapper, ...options }), queryClient };
}

/**
 * Build a `fetch` stub that routes by URL+method to canned responses. Each
 * route is consumed once per match — mock multiple calls by adding the
 * route multiple times. Unmatched calls throw so tests fail loud.
 */
export type FetchRoute = {
  url: string | RegExp;
  method?: string;
  status?: number;
  body?: unknown;
};

export function buildFetchStub(routes: FetchRoute[]): {
  fetchMock: ReturnType<typeof vi.fn>;
  remaining: () => FetchRoute[];
} {
  const queue = [...routes];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    const idx = queue.findIndex((r) => {
      if (r.method && r.method.toUpperCase() !== method) return false;
      return typeof r.url === "string" ? r.url === url : r.url.test(url);
    });
    if (idx === -1) {
      throw new Error(`No fetch route matched ${method} ${url}`);
    }
    const [route] = queue.splice(idx, 1);
    const status = route.status ?? 200;
    const body = route.body === undefined ? null : route.body;
    return new Response(body === null ? "" : JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  });
  return { fetchMock, remaining: () => [...queue] };
}
