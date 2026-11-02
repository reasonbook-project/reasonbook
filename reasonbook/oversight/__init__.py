# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Oversight (Workflow 10) — agency & oversight decision tier.

Per dp/workflows/10-oversight/config.yaml v2.0: covers federal
agency-leadership decisions + statutory and internal oversight
(Inspector General, audit committee) + the response surface for
external oversight (GAO, OMB, Congressional committees).

Renamed from ``apex`` per migration 0036 — the legacy ``apex`` /
``board`` vocabulary is retired throughout code, DB, API, and UI.

Oversight extensions:

- ``evidence`` — link operational determinations / programs / alerts
  as oversight evidence
- ``cycles`` — oversight cycle lifecycle (planned → active → concluded)
- ``authority`` — oversight-specific permission resolution
- ``dossier`` — oversight-cycle PDF generation
"""

OVERSIGHT_WORKFLOW_ID = "10-oversight"

EVIDENCE_ROLES = (
    "primary_evidence",
    "supporting_evidence",
    "risk_concentration_evidence",
    "regulatory_alignment_evidence",
    "outcome_evidence",
    "counter_evidence",
)

DECISION_DOMAINS = (
    "appropriations_and_obligations",
    "program_portfolio",
    "fraud_loss_tolerance",
    "congressional_and_regulatory_posture",
    "subrecipient_and_vendor_oversight",
    "program_design",
    "technology_and_systems",
    "governance_and_organization",
    "governance_improvement",
)
