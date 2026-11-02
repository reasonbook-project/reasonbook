// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import type { WorkflowExtensions } from "..";

import { RegEvidenceView } from "./EvidenceView";
import { RegPayloadView } from "./PayloadView";

export const extensions: WorkflowExtensions = {
  EvidenceView: RegEvidenceView,
  PayloadView: RegPayloadView,
};
