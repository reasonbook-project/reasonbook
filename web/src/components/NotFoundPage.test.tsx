// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Tests for the 404 page rendered on unknown routes (e.g. a legacy URL
 * renamed in the rebrand, or any arbitrary garbage path like
 * ``/cj``). The critical guarantee: it renders OUTSIDE the AppShell so
 * stale deep-links don't look like a broken app.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NotFoundPage } from "./NotFoundPage";

import { useAuthStore } from "@/stores/auth";

function renderAt(path: string) {
  // Mirror the production router shape: a rootRoute with a single
  // dummy `/inbox` child so /inbox matches and unknown paths trigger
  // notFoundComponent.
  const rootRoute = createRootRoute({
    notFoundComponent: NotFoundPage,
  });
  const inboxRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/inbox",
    component: () => <div data-testid="inbox">Inbox</div>,
  });
  const routeTree = rootRoute.addChildren([inboxRoute]);
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("NotFoundPage", () => {
  it("renders for a legacy route renamed in the rebrand", async () => {
    useAuthStore.setState({
      status: "authenticated",
      user: {
        id: "u1",
        username: "test",
        tenant_id: "us-federal",
        tenant_name: "Riverdale",
        name: "Test",
        email: "test@example.com",
        title: null,
        role: "admin",
  tier: "federal" as const,
  participant_org_id: null,
        agency_id: "agency-x",
        agency: { id: "agency-x", slug: "x", name: "X", short_name: "X", depth: 0 },
        agency_chain: [],
        oversight_capabilities: null,
      },
    });

    renderAt("/legacy-route");

    // 404 page renders.
    expect(await screen.findByTestId("not-found-page")).toBeInTheDocument();
    expect(screen.getByText(/that page doesn.t exist/i)).toBeInTheDocument();
    // Authenticated → link points home (Inbox), not to /login.
    expect(screen.getByRole("link", { name: /back to inbox/i })).toHaveAttribute(
      "href",
      "/inbox",
    );
  });

  it("renders for arbitrary unknown paths like /cj", async () => {
    useAuthStore.setState({
      status: "authenticated",
      user: {
        id: "u1",
        username: "test",
        tenant_id: "us-federal",
        tenant_name: "Riverdale",
        name: "Test",
        email: "test@example.com",
        title: null,
        role: "admin",
  tier: "federal" as const,
  participant_org_id: null,
        agency_id: "agency-x",
        agency: { id: "agency-x", slug: "x", name: "X", short_name: "X", depth: 0 },
        agency_chain: [],
        oversight_capabilities: null,
      },
    });

    renderAt("/cj");

    expect(await screen.findByTestId("not-found-page")).toBeInTheDocument();
    expect(screen.queryByTestId("inbox")).not.toBeInTheDocument();
  });

  it("routes anonymous viewers to /login", async () => {
    useAuthStore.setState({ status: "anonymous", user: null });

    renderAt("/cj");

    expect(await screen.findByTestId("not-found-page")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /go to sign in/i })).toHaveAttribute(
      "href",
      "/login",
    );
  });
});
