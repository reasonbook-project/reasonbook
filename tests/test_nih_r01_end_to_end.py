# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""NIH-R01 end-to-end lifecycle — P02 closure test.

Walks an R01 (competitive_award archetype, nih-r01 program profile)
through the BUILD-SPEC Phase 1 closure criteria:

    create → claim → finalize → action → outcome → PDF export

Each stage transition is asserted to:
  - update the Decision row's status/timestamps
  - write an append-only event to {schema_prefix()}decision_events
  - leave the chain intact (no in-place edit; every transition adds a row)

The lifecycle path goes through ``reasonbook.decisions.manager`` directly. The
HTTP path (``POST /api/decisions``) cannot yet originate a federal
program decision because authority resolution still goes through the
legacy workflow registry that doesn't know program ids — see G5 below.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.engine import Engine

from reasonbook.db import session_scope
from reasonbook.db import schema_prefix
from reasonbook.decisions import manager
from reasonbook.models import Decision, DecisionEvent, User
from reasonbook.reports import generate_decision_record_pdf


# --- Helpers -----------------------------------------------------------------


def _uid(username: str) -> uuid.UUID:
    with session_scope() as s:
        return s.query(User).filter(User.username == username).one().id


def _event_actions(decision_id: uuid.UUID) -> list[str]:
    """Append-only event log actions in chronological order."""
    with session_scope() as s:
        rows = (
            s.query(DecisionEvent)
            .filter(DecisionEvent.decision_id == decision_id)
            .order_by(DecisionEvent.created_at.asc())
            .all()
        )
        return [r.action for r in rows]


# --- The walking-skeleton test -----------------------------------------------


def test_nih_r01_walks_all_five_stages(seeded: Engine) -> None:  # noqa: ARG001
    """Demonstrate BUILD-SPEC Phase 1 closure for NIH-R01 via the manager.

    The archetype YAML (competitive_award) declares 5 stages mapping to
    Signal/Owner/Decision/Action/Outcome with `authority_decision` as
    the one authority-gated transition. This test exercises that path
    against the seeded `nih-r01` program (already entitled to riverdale
    in scripts/seed_dev.py).

    Authority resolution honors the program path via G5's
    ``_tenant_can_originate_on_program`` — permissive on program ids
    today, role-aware once G5b lands.
    """
    jamie = _uid("jamie.kim")
    sarah = _uid("sarah.mitchell")  # has agency_head authority — can finalize

    # --- 1. CREATE (Signal stage) -------------------------------------------
    # workflow_id="nih-r01" works here because the program id is smuggled
    # into the workflow_id column today (G1). manager.create_decision
    # itself is workflow-agnostic — it writes the row + 'created' event.
    d = manager.create_decision(
        tenant_id="us-federal",
        workflow_id="nih-r01",
        decision_type="competitive_award",  # the archetype id
        title="R01 application · 5R01CA123456 · Smith et al.",
        created_by=jamie,
        priority="medium",
        sla_hours=1440,  # archetype merit_review SLA hint
        signal_source="manual.test.nih_r01",
        signal_summary="Synthetic R01 application for the lifecycle test",
        trigger_data={
            "application_id": "5R01CA123456",
            "study_section": "CAMP",
            "applicant_org": "Smith University",
        },
    )
    assert d.status == "open"
    assert d.decision_number.startswith("DEC-")
    assert d.signal_captured_at is not None
    assert "created" in _event_actions(d.id)

    # --- 2. CLAIM (Owner stage) ---------------------------------------------
    # State machine: open → in_progress on claim (see manager.TRANSITIONS).
    # 'assigned' is reserved for create-with-owner — separate path.
    manager.claim_decision(decision_id=d.id, user_id=jamie)
    with session_scope() as s:
        d2 = s.get(Decision, d.id)
        assert d2 is not None
        assert d2.status == "in_progress"
        assert d2.owner_id == jamie
        assert d2.acknowledged_at is not None
    assert _event_actions(d.id) == ["created", "claimed"]

    # --- 3. FINALIZE (Decision stage) ---------------------------------------
    # Sarah (agency_head, level 5) has the authority to approve the
    # archetype's 'awarded' outcome. Jamie (program_officer) wouldn't.
    manager.finalize_decision(
        decision_id=d.id,
        user_id=sarah,
        selected_option="awarded",
        rationale=(
            "Impact score 14, percentile 6. Within payline. "
            "Approving per cycle 2 council recommendation."
        ),
        evidence_refs=[
            {"kind": "reviewer_scores", "ref": "study_section_summary.pdf"},
            {"kind": "summary_statement", "ref": "summary_statement.pdf"},
        ],
        alternatives=[
            {"option": "declined", "reason_rejected": "Within payline; merit warrants funding"},
        ],
    )
    with session_scope() as s:
        d3 = s.get(Decision, d.id)
        assert d3 is not None
        assert d3.status == "decided"
        assert d3.selected_option == "awarded"
        assert d3.rationale is not None
        assert d3.decided_at is not None
    assert _event_actions(d.id) == ["created", "claimed", "finalized"]

    # --- 4. ACTION ----------------------------------------------------------
    from datetime import UTC, datetime as _dt

    manager.record_action(
        decision_id=d.id,
        user_id=sarah,
        started_at=_dt.now(UTC),
        artifacts=[
            {"kind": "notice_of_award", "ref": "NIH-NoA-2026-CA123456.pdf"},
        ],
    )
    with session_scope() as s:
        d4 = s.get(Decision, d.id)
        assert d4 is not None
        assert d4.action_started_at is not None
        assert d4.action_artifacts is not None
    assert "action_recorded" in _event_actions(d.id)

    # --- 5. OUTCOME ---------------------------------------------------------
    # outcome_impact is the qualitative classifier (positive/neutral/negative),
    # not the dollar value. Dollar impact lives in outcome_metrics.
    manager.record_outcome(
        decision_id=d.id,
        user_id=sarah,
        outcome_text="Awarded. Year 1 funding obligated 2026-07-01.",
        outcome_impact="positive",
        outcome_metrics={
            "obligated_y1_usd": 487432,
            "project_period_years": 4,
            "impact_score": 14,
            "percentile": 6,
        },
    )
    with session_scope() as s:
        d5 = s.get(Decision, d.id)
        assert d5 is not None
        assert d5.status == "closed"
        assert d5.outcome_text is not None
        assert d5.outcome_metrics is not None
        assert d5.outcome_metrics["impact_score"] == 14
    # All 5 stages have written exactly one event apiece.
    actions = _event_actions(d.id)
    assert actions == ["created", "claimed", "finalized", "action_recorded", "outcome_recorded"]

    # --- 6. PDF EXPORT (Phase 1 closure criterion: examiner-grade PDF) ------
    pdf_bytes = generate_decision_record_pdf(d.id)
    assert pdf_bytes.startswith(b"%PDF-"), "export must be a real PDF"
    assert len(pdf_bytes) > 2000, "PDF must contain substantive content (>2KB)"


def test_pdf_resolves_archetype_stage_labels_for_nih_r01(seeded: Engine) -> None:  # noqa: ARG001
    """G6: PDF stage headers come from the competitive_award archetype +
    nih-r01 program stage_overrides, not generic SIGNAL/OWNER/etc.

    Asserts on the label-resolution helper directly because ReportLab
    compresses the PDF stream — byte-search of generated PDFs is unreliable.
    The helper IS the source of truth; the PDF renderer just consumes it.
    """
    from reasonbook.reports.decision_record import _resolve_stage_labels

    labels = _resolve_stage_labels("nih-r01")
    # From competitive_award archetype YAML stages.label.
    assert labels["signal"] == "APPLICATION RECEIPT"
    assert labels["owner"] == "ELIGIBILITY SCREEN"
    assert labels["decision"] == "MERIT REVIEW"
    # nih-r01 program YAML overrides authority_decision label.
    assert labels["action"] == "ADVISORY COUNCIL & IC DIRECTOR"
    assert labels["outcome"] == "AWARD OR DECLINE"

    # Fallback path — generic labels for unknown workflow ids.
    generic = _resolve_stage_labels("unknown-workflow-id")
    assert generic["signal"] == "SIGNAL"
    assert generic["decision"] == "DECISION"


# --- §6.5 IG outcome taxonomy ------------------------------------------------


def _drive_to_action_stage(jamie: uuid.UUID, sarah: uuid.UUID) -> uuid.UUID:
    """Create + claim + finalize + record_action — leaves a decision ready
    for record_outcome. Used by the outcome-taxonomy tests below."""
    d = manager.create_decision(
        tenant_id="us-federal",
        workflow_id="nih-r01",
        decision_type="competitive_award",
        title="R01 taxonomy fixture",
        created_by=jamie,
        priority="medium",
        sla_hours=1440,
        signal_source="manual.test.outcome_taxonomy",
        signal_summary="Synthetic R01 for outcome-taxonomy assertions",
        trigger_data={"application_id": "5R01CA000000"},
    )
    manager.claim_decision(decision_id=d.id, user_id=jamie)
    manager.finalize_decision(
        decision_id=d.id,
        user_id=sarah,
        selected_option="awarded",
        rationale="Synthetic finalize for taxonomy test.",
    )
    from datetime import UTC, datetime as _dt

    manager.record_action(
        decision_id=d.id,
        user_id=sarah,
        started_at=_dt.now(UTC),
        artifacts=[],
    )
    return d.id


@pytest.mark.parametrize("outcome", manager.LEGAL_OUTCOMES)
def test_legal_outcome_types_accepted(
    seeded: Engine,  # noqa: ARG001
    outcome: str,
) -> None:
    """ARCHITECTURE_MASTER §6.5 — the four IG-consequence outcome types
    (debarment / administrative_recovery / civil_referral /
    criminal_referral) pass validation and persist."""
    jamie = _uid("jamie.kim")
    sarah = _uid("sarah.mitchell")
    did = _drive_to_action_stage(jamie, sarah)
    manager.record_outcome(
        decision_id=did,
        user_id=sarah,
        outcome_text=f"IG outcome: {outcome}.",
        outcome_impact=outcome,
    )
    with session_scope() as s:
        d = s.get(Decision, did)
        assert d is not None
        assert d.outcome_impact == outcome
        assert d.status == "closed"


def test_unknown_outcome_type_rejected(seeded: Engine) -> None:  # noqa: ARG001
    """Validation still rejects values outside the extended taxonomy."""
    jamie = _uid("jamie.kim")
    sarah = _uid("sarah.mitchell")
    did = _drive_to_action_stage(jamie, sarah)
    with pytest.raises(ValueError, match="invalid outcome_impact"):
        manager.record_outcome(
            decision_id=did,
            user_id=sarah,
            outcome_text="bogus value",
            outcome_impact="not_a_real_outcome",
        )


# --- HTTP path: documents the G5 gap so it doesn't drift silently ------------


def test_http_create_for_nih_r01_via_api(
    seeded: Engine,  # noqa: ARG001
    client: Any,
) -> None:
    """HTTP path: POST /api/decisions accepts a program id as workflow_id
    after G5's archetype-aware authority resolution lands.
    """
    from scripts.seed_dev import DEMO_PASSWORD

    login = client.post(
        "/api/auth/login",
        json={"username": "jamie.kim", "password": DEMO_PASSWORD},
    )
    assert login.status_code == 200

    resp = client.post(
        "/api/decisions",
        json={
            "workflow_id": "nih-r01",
            "decision_type": "competitive_award",
            "title": "HTTP-path R01 smoke",
            "signal_summary": "Synthetic R01 via the HTTP create endpoint",
        },
    )
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body["workflow_id"] == "nih-r01"
    assert body["decision_type"] == "competitive_award"
    assert body["status"] == "open"
