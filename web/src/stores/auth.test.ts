// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { beforeEach, describe, expect, it } from "vitest";

import type { CurrentUser } from "@/api/auth";

import { useAuthStore } from "./auth";

const SAMPLE_USER: CurrentUser = {
  id: "user-1",
  username: "jamie.kim",
  name: "Jamie Kim",
  email: "jamie.kim@example.org",
  title: "Program Officer",
  role: "member",
  tenant_id: "us-federal",
  tenant_name: "United States Federal Government",
  tier: "federal" as const,
  participant_org_id: null,
  agency_id: "agency-nih-oer",
  agency: {
    id: "agency-nih-oer",
    slug: "nih-oer",
    name: "NIH Office of Extramural Research",
    short_name: "NIH-OER",
    depth: 2,
  },
  agency_chain: [
    { id: "agency-hhs", slug: "hhs", name: "HHS", short_name: "HHS", depth: 0 },
    { id: "agency-nih", slug: "nih", name: "NIH", short_name: "NIH", depth: 1 },
    {
      id: "agency-nih-oer",
      slug: "nih-oer",
      name: "NIH Office of Extramural Research",
      short_name: "NIH-OER",
      depth: 2,
    },
  ],
  oversight_capabilities: null,
};

describe("useAuthStore", () => {
  beforeEach(() => {
    useAuthStore.setState({ status: "unknown", user: null });
  });

  it("starts in unknown state", () => {
    expect(useAuthStore.getState().status).toBe("unknown");
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("setUser(user) flips status to authenticated", () => {
    useAuthStore.getState().setUser(SAMPLE_USER);
    expect(useAuthStore.getState().status).toBe("authenticated");
    expect(useAuthStore.getState().user).toEqual(SAMPLE_USER);
  });

  it("setUser(null) flips status to anonymous", () => {
    useAuthStore.getState().setUser(SAMPLE_USER);
    useAuthStore.getState().setUser(null);
    expect(useAuthStore.getState().status).toBe("anonymous");
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("reset() clears state to anonymous", () => {
    useAuthStore.getState().setUser(SAMPLE_USER);
    useAuthStore.getState().reset();
    expect(useAuthStore.getState().status).toBe("anonymous");
    expect(useAuthStore.getState().user).toBeNull();
  });
});
