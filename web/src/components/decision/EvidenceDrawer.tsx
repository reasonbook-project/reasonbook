// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMemo, useState } from "react";

import type { Matter, MatterDecision } from "@/api/matters";
import { Drawer } from "@/components/ds/Drawer";
import { cn } from "@/lib/cn";

/**
 * EvidenceDrawer — right-side slide-in that surfaces the evidence
 * attached to a decision (or all decisions on a matter).
 *
 * Per docs/architecture/_archive/ui-improvements/04-decision-detail-options.html
 * (Composite · Evidence in drawer section).
 *
 * Shape:
 *   Header   Title + item count + close ×
 *   Scope    This decision | All on matter · N
 *   Attach   Dashed drop-zone (visual only in this pass)
 *   List     Grouped evidence rows with kind chip · title · meta · actions
 *
 * The items list is derived from MatterDecision.evidence_refs; every
 * ref becomes a row with mock-enriched metadata so the drawer reads
 * well before a richer evidence backend lands.
 */

export type EvidenceItem = {
  id: string;
  decisionId: string;
  decisionNumber: string;
  kind: EvidenceKind;
  title: string;
  meta: string;
  primaryAction?: string;
  secondaryAction?: string;
};

export type EvidenceKind =
  | "auto_flag"
  | "attachment"
  | "tier_accept"
  | "cite"
  | "link";

export function EvidenceDrawer({
  open,
  onClose,
  matter,
  focusDecisionId,
  matterLabel,
}: {
  open: boolean;
  onClose: () => void;
  matter: Matter;
  /** Which decision the drawer opened on. Null = All-on-matter scope. */
  focusDecisionId: string | null;
  /** Compact label for the matter shown in the header when scope=all
   *  (e.g. the program id "cdbg-fy26"). */
  matterLabel?: string;
}) {
  const [scope, setScope] = useState<"this" | "all">(
    focusDecisionId ? "this" : "all",
  );

  const focusDecision = useMemo(
    () => matter.decisions.find((d) => d.id === focusDecisionId) ?? null,
    [matter.decisions, focusDecisionId],
  );

  const items = useMemo(() => deriveItems(matter), [matter]);
  const scopedItems = useMemo(() => {
    if (scope === "this" && focusDecisionId) {
      return items.filter((it) => it.decisionId === focusDecisionId);
    }
    return items;
  }, [items, scope, focusDecisionId]);

  const titleLabel =
    scope === "this" && focusDecision
      ? focusDecision.decision_number
      : (matterLabel ?? matter.program_id ?? "matter");

  return (
    <Drawer
      open={open}
      onClose={onClose}
      ariaLabel="Evidence drawer"
      width={520}
    >
      <div className="flex h-full flex-col">
        {/* Header */}
        <header className="flex items-center gap-2 px-4 py-3 border-b-[0.5px] border-rule-soft bg-paper-warm/60">
          <div className="flex items-baseline gap-2">
            <span className="font-display font-medium text-[15px] text-ink">
              Evidence
            </span>
            <span className="text-ink-faint text-[12px]">·</span>
            <span className="font-mono text-[12px] text-ink-soft">
              {titleLabel}
            </span>
            <span
              className="ml-1 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-[#7c3aed] text-paper text-[10px] font-mono font-medium"
              aria-label={`${scopedItems.length} items`}
            >
              {scopedItems.length}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto text-[16px] leading-none text-ink-muted hover:text-ink px-1"
            aria-label="Close"
          >
            ×
          </button>
        </header>

        {/* Scope tabs */}
        <div className="flex items-center gap-1 px-4 py-2 border-b-[0.5px] border-rule-soft bg-paper">
          <ScopeTab
            active={scope === "this"}
            disabled={!focusDecisionId}
            onClick={() => setScope("this")}
          >
            This decision
            {focusDecisionId && (
              <span className="ml-1.5 text-ink-faint">
                · {items.filter((it) => it.decisionId === focusDecisionId).length}
              </span>
            )}
          </ScopeTab>
          <ScopeTab
            active={scope === "all"}
            onClick={() => setScope("all")}
          >
            All on matter
            <span className="ml-1.5 text-ink-faint">· {items.length}</span>
          </ScopeTab>
        </div>

        {/* Attach zone */}
        <div className="px-4 pt-3 pb-2">
          <button
            type="button"
            className={cn(
              "w-full rounded-md border border-dashed border-rule",
              "bg-paper-warm/40 px-3 py-3 text-[12px] text-ink-muted",
              "hover:border-navy hover:text-ink-soft transition-colors",
              "flex items-center justify-center gap-2",
            )}
            onClick={() => {
              /* attach lands in a follow-up */
            }}
          >
            <span aria-hidden>📎</span>
            <span>Drag files here or click to attach</span>
            <span className="text-ink-faint/70">· CSV, PDF, PNG, ...</span>
          </button>
        </div>

        {/* Items list */}
        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-2">
          {scopedItems.length === 0 ? (
            <div className="py-10 text-center text-[12.5px] text-ink-muted italic">
              No evidence recorded yet.
            </div>
          ) : (
            <ul className="divide-y-[0.5px] divide-rule-faint">
              {scope === "all" ? (
                <GroupedRows
                  items={scopedItems}
                  focusDecisionId={focusDecisionId}
                />
              ) : (
                scopedItems.map((it) => <EvidenceRow key={it.id} item={it} />)
              )}
            </ul>
          )}
        </div>
      </div>
    </Drawer>
  );
}

/* ─── Scope tab ───────────────────────────────────────────────────── */

function ScopeTab({
  active,
  disabled = false,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "px-2.5 py-1 rounded-sm text-[11.5px] font-medium tracking-[0.02em]",
        "transition-colors",
        active
          ? "bg-navy text-paper"
          : disabled
            ? "text-ink-faint/60 cursor-not-allowed"
            : "text-ink-soft hover:bg-bg-warm",
      )}
    >
      {children}
    </button>
  );
}

/* ─── Grouped rows (when scope = all) ─────────────────────────────── */

function GroupedRows({
  items,
  focusDecisionId,
}: {
  items: EvidenceItem[];
  focusDecisionId: string | null;
}) {
  // Preserve focus decision first, then remaining by decisionNumber.
  const groups = useMemo(() => {
    const byDecision = new Map<string, EvidenceItem[]>();
    for (const it of items) {
      const arr = byDecision.get(it.decisionId) ?? [];
      arr.push(it);
      byDecision.set(it.decisionId, arr);
    }
    const entries = Array.from(byDecision.entries());
    entries.sort(([a], [b]) => {
      if (a === focusDecisionId) return -1;
      if (b === focusDecisionId) return 1;
      const aItem = byDecision.get(a)![0];
      const bItem = byDecision.get(b)![0];
      return aItem.decisionNumber.localeCompare(bItem.decisionNumber);
    });
    return entries;
  }, [items, focusDecisionId]);

  return (
    <>
      {groups.map(([decId, decItems]) => (
        <li key={decId} className="py-2">
          <div className="mb-1 flex items-baseline gap-2 text-[10px] uppercase tracking-[0.08em] text-ink-faint font-medium">
            <span>{decItems[0].decisionNumber}</span>
            {decId === focusDecisionId && (
              <span className="normal-case tracking-normal text-navy">
                · this decision
              </span>
            )}
          </div>
          <ul className="divide-y-[0.5px] divide-rule-faint">
            {decItems.map((it) => (
              <EvidenceRow key={it.id} item={it} />
            ))}
          </ul>
        </li>
      ))}
    </>
  );
}

/* ─── Row ─────────────────────────────────────────────────────────── */

function EvidenceRow({ item }: { item: EvidenceItem }) {
  return (
    <li className="py-2.5 flex items-start gap-2.5">
      <KindChip kind={item.kind} />
      <div className="flex-1 min-w-0">
        <div className="text-[12.5px] text-ink font-medium truncate">
          {item.title}
        </div>
        <div className="text-[11px] text-ink-faint mt-0.5 truncate">
          {item.meta}
        </div>
      </div>
      <div className="flex items-center gap-2 text-[11px]">
        {item.primaryAction && (
          <button
            type="button"
            className="text-navy hover:underline"
          >
            {item.primaryAction}
          </button>
        )}
        {item.secondaryAction && (
          <button
            type="button"
            className="text-ink-faint hover:text-ink hover:underline"
          >
            {item.secondaryAction}
          </button>
        )}
      </div>
    </li>
  );
}

function KindChip({ kind }: { kind: EvidenceKind }) {
  const label = KIND_LABEL[kind];
  const palette = KIND_PALETTE[kind];
  return (
    <span
      className={cn(
        "shrink-0 mt-0.5 inline-flex items-center px-1.5 py-0.5 rounded-sm",
        "text-[9.5px] uppercase tracking-[0.06em] font-mono font-medium",
        palette,
      )}
    >
      {label}
    </span>
  );
}

const KIND_LABEL: Record<EvidenceKind, string> = {
  auto_flag: "auto-flag",
  attachment: "attach",
  tier_accept: "tier-accept",
  cite: "cite",
  link: "link",
};

const KIND_PALETTE: Record<EvidenceKind, string> = {
  auto_flag: "bg-[#fee2e2] text-[#9c1c1c]",
  attachment: "bg-bg-warm text-ink-soft",
  tier_accept: "bg-cleared/15 text-cleared",
  cite: "bg-navy-soft text-navy-deep",
  link: "bg-bg-warm text-ink-soft",
};

/* ─── Derivation from decision.evidence_refs ─────────────────────── */

/**
 * Turn each decision's evidence_refs into rendered rows. Mock-enriches
 * the sparse `{kind, ref}` shape with a title / meta / actions so the
 * drawer reads like a real evidence surface until a richer evidence
 * backend lands.
 */
function deriveItems(matter: Matter): EvidenceItem[] {
  const items: EvidenceItem[] = [];
  for (const d of matter.decisions) {
    const refs = d.evidence_refs ?? [];
    refs.forEach((ref, i) => {
      items.push(enrichRef(d, ref, i));
    });
  }
  return items;
}

function enrichRef(
  d: MatterDecision,
  ref: { kind: string; ref: string },
  idx: number,
): EvidenceItem {
  const kind = normalizeKind(ref.kind);
  const base = {
    id: `${d.id}-${idx}`,
    decisionId: d.id,
    decisionNumber: d.decision_number,
    kind,
  };
  switch (kind) {
    case "auto_flag":
      return {
        ...base,
        title: prettyRef(ref.ref, "Auto-flag"),
        meta: `flagged during signal review · ${ref.ref}`,
        primaryAction: "View raw",
        secondaryAction: "Re-run",
      };
    case "attachment":
      return {
        ...base,
        title: prettyRef(ref.ref, "Attachment"),
        meta: `uploaded to case file · ${ref.ref}`,
        primaryAction: "Open",
        secondaryAction: "Download",
      };
    case "tier_accept":
      return {
        ...base,
        title: prettyRef(ref.ref, "Tier-accept record"),
        meta: `stamped on acceptance · ${ref.ref}`,
        primaryAction: "View",
      };
    case "cite":
      return {
        ...base,
        title: prettyRef(ref.ref, "Cited authority"),
        meta: `${ref.ref}`,
        primaryAction: "Open",
      };
    case "link":
    default:
      return {
        ...base,
        title: prettyRef(ref.ref, "Linked reference"),
        meta: `${ref.ref}`,
        primaryAction: "Open",
      };
  }
}

function normalizeKind(k: string): EvidenceKind {
  const lower = k.toLowerCase().trim();
  if (lower.includes("flag") || lower.includes("anomaly")) return "auto_flag";
  if (lower.includes("attach") || lower.includes("upload")) return "attachment";
  if (lower.includes("tier") || lower.includes("accept")) return "tier_accept";
  if (lower.includes("cite") || lower.includes("cfr") || lower.includes("§"))
    return "cite";
  return "link";
}

function prettyRef(ref: string, fallback: string): string {
  const trimmed = ref.trim();
  if (!trimmed) return fallback;
  // Strip everything before the last "/" for URL-ish refs
  const tail = trimmed.split("/").pop() ?? trimmed;
  if (tail.length > 6) return tail;
  return trimmed;
}

/* ─── Public helpers ──────────────────────────────────────────────── */

/** Count evidence items for a single decision. Used by the header chip. */
export function evidenceCountFor(d: MatterDecision): number {
  return (d.evidence_refs ?? []).length;
}

/** Whether any auto-flag / anomaly evidence is present — drives chip color. */
export function hasFlagEvidence(d: MatterDecision): boolean {
  return (d.evidence_refs ?? []).some(
    (r) => normalizeKind(r.kind) === "auto_flag",
  );
}
