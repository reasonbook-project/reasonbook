// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";

import { catalogExportUrl } from "./workflows";

describe("catalogExportUrl", () => {
  it("omits workflow_ids param when no workflows passed (backend defaults to all entitled)", () => {
    expect(catalogExportUrl([], "yaml")).toBe(
      "/api/catalog/export?format=yaml",
    );
  });

  it("appends workflow_ids when filtered to a subset", () => {
    expect(catalogExportUrl(["01-regulatory-compliance"], "json")).toBe(
      "/api/catalog/export?format=json&workflow_ids=01-regulatory-compliance",
    );
  });

  it("comma-joins multiple workflow ids in the order passed", () => {
    expect(
      catalogExportUrl(["01-regulatory-compliance", "01-regulatory-compliance"], "yaml"),
    ).toBe(
      "/api/catalog/export?format=yaml&workflow_ids=01-regulatory-compliance,01-regulatory-compliance",
    );
  });
});
