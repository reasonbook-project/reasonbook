# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Matter case file PDF — the artefact that travels.

Per docs/architecture/SURFACE-USER-STORIES.md, the case file is the
self-contained, authoritative, tamper-evident record of a single
federal-award matter. It's what OIG / 3PAO / congressional staff /
DOJ AUSA / GAO / program officers attach to their own records —
verifiable without DP credentials.

Structure mirrors the on-screen case file (web/src/routes/matterDetail.tsx):

  Cover              masthead + matter identification
  §0 · Integrity certificate (head hash + verified-at + total events)
  §1 · Award identification (kv table)
  §2 · Fund-flow path (text tree with per-edge amounts)
  §3 · Open signals (when present)
  §4 · Decision records (per-tier collection)
  §5 · Audit chain (chronological event log across every decision in the matter)

Borrows the design-token palette and footer chrome from
dp/reports/decision_record.py so the two artefacts read as siblings.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from reasonbook.db import session_scope
from reasonbook.integrity import verify_chain
from reasonbook.models import (
    Alert,
    Decision,
    DecisionEvent,
    Matter,
    MatterNode,
    ParticipantOrg,
    User,
)

# Mirrored from dp/reports/decision_record.py — keep in sync with
# web/src/index.css §3 design tokens.
BRAND_BLUE = colors.HexColor("#3162AA")
DEEP_NAVY = colors.HexColor("#042C53")
INK = colors.HexColor("#1A1A1A")
INK_SECONDARY = colors.HexColor("#5A5A5A")
INK_TERTIARY = colors.HexColor("#9A9A9A")
HAIRLINE = colors.HexColor("#E2E2DD")
WARM_GROUND = colors.HexColor("#FAFAF7")
SIGNAL_RED_TEXT = colors.HexColor("#9C1C1C")
SIGNAL_RED_BG = colors.HexColor("#FEF2F2")
CHAIN_OK_GREEN = colors.HexColor("#15803D")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = base["BodyText"]
    return {
        "masthead": ParagraphStyle(
            "masthead",
            parent=body,
            fontName="Times-Roman",
            fontSize=22,
            leading=26,
            textColor=DEEP_NAVY,
            spaceAfter=2,
        ),
        "eyebrow": ParagraphStyle(
            "eyebrow",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=INK_TERTIARY,
            spaceAfter=4,
        ),
        "subhead": ParagraphStyle(
            "subhead",
            parent=body,
            fontName="Helvetica",
            fontSize=11,
            textColor=INK_SECONDARY,
            spaceAfter=14,
        ),
        "section": ParagraphStyle(
            "section",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=INK_SECONDARY,
            spaceBefore=18,
            spaceAfter=6,
        ),
        "label": ParagraphStyle(
            "label",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=INK_TERTIARY,
            spaceAfter=2,
        ),
        "value": ParagraphStyle(
            "value",
            parent=body,
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=INK,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            parent=body,
            fontName="Helvetica",
            fontSize=10,
            leading=15,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "mono": ParagraphStyle(
            "mono",
            parent=body,
            fontName="Courier",
            fontSize=9,
            leading=12,
            textColor=INK_SECONDARY,
        ),
        "signal_title": ParagraphStyle(
            "signal_title",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=SIGNAL_RED_TEXT,
            spaceAfter=2,
        ),
        "tree": ParagraphStyle(
            "tree",
            parent=body,
            fontName="Courier",
            fontSize=10,
            leading=14,
            textColor=INK,
            spaceAfter=1,
        ),
    }


def _draw_footer(canvas: Any, doc: Any) -> None:
    canvas.saveState()
    width, _ = LETTER
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(INK_TERTIARY)
    canvas.drawString(
        0.75 * inch,
        0.5 * inch,
        "Generated by Reasonbook",
    )
    canvas.drawRightString(width - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.setStrokeColor(HAIRLINE)
    canvas.setLineWidth(0.5)
    canvas.line(0.75 * inch, 0.7 * inch, width - 0.75 * inch, 0.7 * inch)
    canvas.restoreState()


def _kv_table(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    data = [
        [Paragraph(label, styles["label"]), Paragraph(value or "—", styles["value"])]
        for label, value in rows
    ]
    table = Table(data, colWidths=[1.6 * inch, 5.0 * inch])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _format_money(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.0f}"


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%b %d, %Y · %I:%M %p %Z").strip()


def _status_label(status: str | None) -> str:
    if not status:
        return "—"
    return status[:1].upper() + status[1:].replace("_", " ")


def _esc(text: str | None) -> str:
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ────────────────────────────────────────────────────────────────────
# Section builders
# ────────────────────────────────────────────────────────────────────


def _integrity_section(
    session: Any, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    """§0 · Integrity certificate — head hash + verify-chain result."""
    result = verify_chain(session)
    verified_at = datetime.now(UTC).strftime("%b %d, %Y · %I:%M %p UTC")
    status_text = (
        "<font color='#15803d'><b>VERIFIED</b></font>"
        if result.ok
        else "<font color='#9c1c1c'><b>BROKEN</b></font>"
    )
    head = result.head_hash or "—"
    head_short = head[:16] + "…" if len(head) > 17 else head

    flow: list[Any] = []
    flow.append(Paragraph("§0 · INTEGRITY CERTIFICATE", styles["section"]))
    flow.append(
        Paragraph(
            "This record derives from a hash-chained ledger that cannot "
            "be silently rewritten. The chain was re-walked from genesis "
            "at the moment this PDF was generated and confirmed against "
            "every stored hash. The reader can independently re-verify "
            "from the underlying <font name='Courier'>decision_events</font> "
            "table at any time.",
            styles["body"],
        )
    )
    flow.append(
        _kv_table(
            [
                ("Chain status", status_text),
                ("Head hash", head_short),
                ("Total events", str(result.total_events)),
                ("Verified at", verified_at),
            ],
            styles,
        )
    )
    if not result.ok:
        flow.append(
            Paragraph(
                f"<b>Chain break detected</b> at event index "
                f"{result.broken_at_index} (id {result.broken_at_id}). "
                "This case file should not be relied on until the break "
                "is investigated.",
                styles["body"],
            )
        )
    return flow


def _identification_section(
    matter: Matter, styles: dict[str, ParagraphStyle]
) -> list[Any]:
    flow: list[Any] = [Paragraph("§1 · AWARD IDENTIFICATION", styles["section"])]
    flow.append(
        _kv_table(
            [
                ("Awarding agency", _esc(matter.awarding_agency)),
                ("Program", _esc(matter.program_id)),
                ("Archetype", _esc(matter.federal_archetype)),
                ("Period", _esc(matter.period_label or "—")),
                ("Amount obligated", _format_money(matter.amount_obligated)),
                ("Terms", _esc(matter.terms or "—")),
                (
                    "Retention",
                    f"{matter.retention_months} months"
                    if matter.retention_months
                    else "—",
                ),
                ("Matter id", str(matter.id)),
            ],
            styles,
        )
    )
    return flow


def _fund_flow_section(
    matter: Matter,
    nodes: list[MatterNode],
    org_lookup: dict[uuid.UUID, ParticipantOrg],
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    """§2 · Fund-flow path — text tree, agency → state → recipients.

    The PDF format renders the same tree the on-screen FundFlowGraph
    visualizes — one line per node with per-edge dollar amounts.
    """
    flow: list[Any] = [Paragraph("§2 · FUND-FLOW PATH", styles["section"])]

    federal_root: MatterNode | None = None
    by_parent: dict[uuid.UUID, list[MatterNode]] = {}
    for n in nodes:
        if n.parent_node_id is None and n.tier == "federal":
            federal_root = n
        elif n.parent_node_id is not None:
            by_parent.setdefault(n.parent_node_id, []).append(n)

    if federal_root is None:
        flow.append(
            Paragraph("(Fund-flow tree unavailable for this matter.)", styles["value"])
        )
        return flow

    def label_for(node: MatterNode) -> str:
        if node.tier == "federal":
            return matter.awarding_agency
        org = (
            org_lookup.get(node.participant_org_id)
            if node.participant_org_id
            else None
        )
        return org.display_name if org else node.tier.title()

    lines: list[str] = []
    # Federal root
    lines.append(
        f"AGENCY    {_format_money(federal_root.amount):>14}    {label_for(federal_root)}"
    )
    for state in by_parent.get(federal_root.id, []):
        lines.append(
            f"  STATE   {_format_money(state.amount):>14}    {label_for(state)}"
        )
        for recip in by_parent.get(state.id, []):
            lines.append(
                f"    RECIP {_format_money(recip.amount):>14}    {label_for(recip)}"
            )
            for sub in by_parent.get(recip.id, []):
                lines.append(
                    f"      SUB {_format_money(sub.amount):>14}    {label_for(sub)}"
                )

    for line in lines:
        flow.append(Paragraph(_esc(line).replace(" ", "&nbsp;"), styles["tree"]))
    flow.append(Spacer(1, 6))
    flow.append(
        Paragraph(
            "Per-node amounts reflect the dollar exposure that arrived AT "
            "each participant. Federal-direct awards (no state "
            "pass-through) hang the recipient straight off the agency.",
            styles["body"],
        )
    )
    return flow


def _signals_section(
    alerts: list[Alert], styles: dict[str, ParagraphStyle]
) -> list[Any]:
    flow: list[Any] = [Paragraph("§3 · OPEN SIGNALS", styles["section"])]
    if not alerts:
        flow.append(
            Paragraph("No open signals on this matter.", styles["value"])
        )
        return flow
    for a in alerts:
        ref = a.signal_ref or {}
        flow.append(Paragraph(f"⚠ {_esc(a.title)}", styles["signal_title"]))
        if a.body:
            flow.append(Paragraph(_esc(a.body), styles["body"]))
        rows: list[tuple[str, str]] = [
            ("Severity", _esc(a.severity)),
            ("Kind", _esc(ref.get("kind") or "—")),
        ]
        if ref.get("expected_parent"):
            rows.append(("Expected pass-through", _esc(ref["expected_parent"])))
        if ref.get("skipped_tier"):
            rows.append(("Skipped tier", _esc(ref["skipped_tier"])))
        flow.append(_kv_table(rows, styles))
        flow.append(Spacer(1, 6))
    return flow


def _decision_records_section(
    matter: Matter,
    decisions: list[Decision],
    nodes_by_id: dict[uuid.UUID, MatterNode],
    org_lookup: dict[uuid.UUID, ParticipantOrg],
    styles: dict[str, ParagraphStyle],
    *,
    section_number: int,
) -> list[Any]:
    """§4 · Decision records — every consequential participant's stamp.

    Grouped by tier so the reader sees federal → state → recipient
    decisions in the order money flows. An "Investigative & authority
    actions" trailing group catches anything that isn't a tier-accept.
    """
    flow: list[Any] = [
        Paragraph(f"§{section_number} · DECISION RECORDS", styles["section"]),
        Paragraph(
            f"{len(decisions)} decision{'s' if len(decisions) != 1 else ''} held "
            "by this matter. Every consequential participant's stamp, booked.",
            styles["body"],
        ),
    ]

    def tier_of(d: Decision) -> str:
        node = nodes_by_id.get(d.matter_node_id) if d.matter_node_id else None
        return node.tier if node else "federal"

    def participant_of(d: Decision) -> str:
        node = nodes_by_id.get(d.matter_node_id) if d.matter_node_id else None
        if node is None or node.tier == "federal":
            return matter.awarding_agency
        org = (
            org_lookup.get(node.participant_org_id)
            if node.participant_org_id
            else None
        )
        return org.display_name if org else "—"

    tier_acceptance = [
        d for d in decisions if d.signal_source == "tier_accept" or d.id == matter.originating_decision_id
    ]
    layered = [d for d in decisions if d not in tier_acceptance]

    def add_group(label: str, items: list[Decision]) -> None:
        if not items:
            return
        flow.append(Spacer(1, 4))
        flow.append(Paragraph(label, styles["label"]))
        rows: list[list[Any]] = [
            [
                Paragraph("<b>#</b>", styles["mono"]),
                Paragraph("<b>Tier</b>", styles["mono"]),
                Paragraph("<b>Participant</b>", styles["mono"]),
                Paragraph("<b>Title</b>", styles["mono"]),
                Paragraph("<b>Status</b>", styles["mono"]),
                Paragraph("<b>Decided</b>", styles["mono"]),
            ]
        ]
        for d in items:
            rows.append(
                [
                    Paragraph(_esc(d.decision_number), styles["mono"]),
                    Paragraph(_esc(tier_of(d)), styles["value"]),
                    Paragraph(_esc(participant_of(d)), styles["value"]),
                    Paragraph(_esc(d.title), styles["value"]),
                    Paragraph(_esc(_status_label(d.status)), styles["value"]),
                    Paragraph(_format_dt(d.decided_at), styles["mono"]),
                ]
            )
        t = Table(
            rows,
            colWidths=[
                0.9 * inch,
                0.7 * inch,
                1.6 * inch,
                1.9 * inch,
                0.7 * inch,
                0.8 * inch,
            ],
            repeatRows=1,
        )
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, HAIRLINE),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, HAIRLINE),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ("BACKGROUND", (0, 0), (-1, 0), WARM_GROUND),
                ]
            )
        )
        flow.append(t)

    add_group("Per-tier acceptance", tier_acceptance)
    add_group("Investigative & authority actions", layered)
    return flow


def _audit_chain_section(
    events: list[DecisionEvent],
    decisions_by_id: dict[uuid.UUID, Decision],
    users_by_id: dict[uuid.UUID, User],
    styles: dict[str, ParagraphStyle],
    *,
    section_number: int,
) -> list[Any]:
    """§5 · Audit chain — chronological event log across the matter.

    Each row links the per-decision number, the action, the status
    transition, the actor, and the event's hash prefix so the reader
    can cross-reference back into ``decision_events``.
    """
    flow: list[Any] = [Paragraph(f"§{section_number} · AUDIT CHAIN", styles["section"])]
    if not events:
        flow.append(
            Paragraph(
                "No events recorded on the decisions in this matter.",
                styles["value"],
            )
        )
        return flow

    rows: list[list[Any]] = [
        [
            Paragraph("<b>Time</b>", styles["mono"]),
            Paragraph("<b>Decision</b>", styles["mono"]),
            Paragraph("<b>Action</b>", styles["mono"]),
            Paragraph("<b>Transition</b>", styles["mono"]),
            Paragraph("<b>Actor</b>", styles["mono"]),
            Paragraph("<b>Hash</b>", styles["mono"]),
        ]
    ]
    for e in events:
        d = decisions_by_id.get(e.decision_id)
        u = users_by_id.get(e.user_id) if e.user_id else None
        rows.append(
            [
                Paragraph(_format_dt(e.created_at), styles["mono"]),
                Paragraph(_esc(d.decision_number) if d else "—", styles["mono"]),
                Paragraph(_esc(e.action), styles["value"]),
                Paragraph(
                    f"{_esc(e.old_status) or '—'} → {_esc(e.new_status) or '—'}",
                    styles["mono"],
                ),
                Paragraph(_esc(u.name) if u else "(system)", styles["value"]),
                Paragraph(_esc((e.hash or "")[:10]), styles["mono"]),
            ]
        )
    t = Table(
        rows,
        colWidths=[
            1.3 * inch,
            0.9 * inch,
            0.9 * inch,
            1.2 * inch,
            1.4 * inch,
            0.9 * inch,
        ],
        repeatRows=1,
    )
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, HAIRLINE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, HAIRLINE),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("BACKGROUND", (0, 0), (-1, 0), WARM_GROUND),
            ]
        )
    )
    flow.append(t)
    return flow


# ────────────────────────────────────────────────────────────────────
# Top-level entry
# ────────────────────────────────────────────────────────────────────


def generate_matter_case_file_pdf(matter_id: uuid.UUID) -> bytes:
    """Render the case-file PDF for a single matter.

    Returns an empty bytes object when the matter isn't found — caller
    should 404 instead of attempting download.
    """
    with session_scope() as session:
        matter = session.get(Matter, matter_id)
        if matter is None:
            return b""

        nodes = (
            session.query(MatterNode)
            .filter(MatterNode.matter_id == matter.id)
            .filter(MatterNode.removed_at.is_(None))
            .order_by(MatterNode.added_at.asc())
            .all()
        )
        nodes_by_id = {n.id: n for n in nodes}
        org_ids = {n.participant_org_id for n in nodes if n.participant_org_id}
        org_lookup: dict[uuid.UUID, ParticipantOrg] = {}
        if org_ids:
            org_lookup = {
                o.id: o
                for o in session.query(ParticipantOrg)
                .filter(ParticipantOrg.id.in_(org_ids))
                .all()
            }

        decisions = (
            session.query(Decision)
            .filter(Decision.matter_id == matter.id)
            .order_by(Decision.created_at.asc())
            .all()
        )
        decisions_by_id = {d.id: d for d in decisions}

        events: list[DecisionEvent] = []
        if decisions:
            events = (
                session.query(DecisionEvent)
                .filter(DecisionEvent.decision_id.in_([d.id for d in decisions]))
                .order_by(DecisionEvent.created_at.asc(), DecisionEvent.id.asc())
                .all()
            )

        user_ids = {e.user_id for e in events if e.user_id}
        users_by_id: dict[uuid.UUID, User] = {}
        if user_ids:
            users_by_id = {
                u.id: u
                for u in session.query(User).filter(User.id.in_(user_ids)).all()
            }

        alerts = (
            session.query(Alert)
            .filter(Alert.matter_id == matter.id)
            .filter(Alert.current_status.in_(("new", "reopened")))
            .order_by(Alert.detected_at.asc())
            .all()
        )

        styles = _styles()
        buf = BytesIO()
        doc = BaseDocTemplate(
            buf,
            pagesize=LETTER,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.85 * inch,
            title=f"Matter case file — {matter.id.hex[:8]}",
            author="Reasonbook",
        )
        frame = Frame(
            doc.leftMargin,
            doc.bottomMargin,
            doc.width,
            doc.height,
            id="body",
        )
        doc.addPageTemplates(
            [PageTemplate(id="default", frames=[frame], onPage=_draw_footer)]
        )

        story: list[Any] = []
        # Cover
        story.append(Paragraph("Reasonbook", styles["masthead"]))
        story.append(
            Paragraph(
                "Matter case file · formal record of a federal-award matter",
                styles["eyebrow"],
            )
        )
        story.append(
            Paragraph(
                f"{_esc(matter.awarding_agency)} · {_esc(matter.program_id)} · "
                f"{_esc(matter.period_label or '')}",
                styles["subhead"],
            )
        )

        story.extend(_integrity_section(session, styles))
        story.extend(_identification_section(matter, styles))
        story.extend(_fund_flow_section(matter, nodes, org_lookup, styles))

        # Section numbering compresses when there are no open signals,
        # matching the on-screen case file's §3/§4 vs §4/§5 behaviour.
        next_section = 3
        if alerts:
            story.extend(_signals_section(alerts, styles))
            next_section = 4
        story.extend(
            _decision_records_section(
                matter,
                decisions,
                nodes_by_id,
                org_lookup,
                styles,
                section_number=next_section,
            )
        )
        story.extend(
            _audit_chain_section(
                events,
                decisions_by_id,
                users_by_id,
                styles,
                section_number=next_section + 1,
            )
        )

        doc.build(story)
        return buf.getvalue()
