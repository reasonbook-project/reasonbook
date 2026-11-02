// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import type { WorkflowExtensions } from "..";

import { OversightEvidenceView } from "./EvidenceView";
import { OversightPayloadView } from "./PayloadView";

export const extensions: WorkflowExtensions = {
  EvidenceView: OversightEvidenceView,
  PayloadView: OversightPayloadView,
};
