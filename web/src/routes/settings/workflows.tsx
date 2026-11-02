// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { Button } from "@/components/ds/Button";
import { type Mode } from "@/components/ds/ModeTabs";
import { HelpLink } from "@/components/help/HelpLink";
import { SettingsLayout } from "@/components/settings/SettingsLayout";
import {
  useOverrideHistory,
  useSetOverride,
  useSupersedeOverride,
  useWorkflowSettings,
} from "@/hooks/useSettings";
import { useWorkflows } from "@/hooks/useWorkflows";

import { rootRoute } from "../__root";

/**
 * /settings/workflows — workflow-config surface.
 *
 *  - No `id`: overview of every entitled workflow.
 *  - `?id=<workflowId>`: per-workflow detail with mode tabs
 *    (Schema / Overrides / Personas / Connectors).
 *
 * The Settings tree (see SettingsLayout) lists every entitled
 * workflow under "Semantic engine"; clicking a workflow lands here
 * with the id pre-set. The semantic engine — workflow YAMLs +
 * tenant overrides + persona config — is where the rules that
 * govern signals and decisions live.
 */
type WorkflowMode = "schema" | "overrides" | "personas";
const VALID_MODES: ReadonlyArray<WorkflowMode> = [
  "schema",
  "overrides",
  "personas",
];

export const settingsWorkflowsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/workflows",
  validateSearch: (search: Record<string, unknown>): {
    id?: string;
    mode?: WorkflowMode;
  } => {
    const id = typeof search.id === "string" ? search.id : undefined;
    const m =
      typeof search.mode === "string" &&
      (VALID_MODES as string[]).includes(search.mode)
        ? (search.mode as WorkflowMode)
        : undefined;
    return { id, mode: m };
  },
  component: WorkflowsPage,
});

function WorkflowsPage() {
  const { id, mode: modeParam } = settingsWorkflowsRoute.useSearch();
  const navigate = useNavigate();
  const workflowsQuery = useWorkflows();
  const list = (workflowsQuery.data?.workflows ?? []).filter(
    (w) => w.kind !== "user_configuration",
  );
  const selected = id ? list.find((w) => w.id === id) ?? null : null;
  const mode: WorkflowMode = modeParam ?? "overrides";

  const setMode = (m: WorkflowMode) =>
    void navigate({
      to: "/settings/workflows",
      search: { id, mode: m },
    });

  if (!selected) {
    return (
      <SettingsLayout
        title="Workflows"
        subtitle={`${list.length} entitled · semantic-engine rules`}
      >
        <p className="text-[13px] text-ink-soft mb-4">
          Pick a workflow from the tree on the left to inspect its
          schema, edit overrides, set personas, or wire connectors.
        </p>
        <ul className="border-[0.5px] border-rule rounded-md overflow-hidden">
          {list.map((w) => (
            <li
              key={w.id}
              className="border-b-[0.5px] border-rule-faint last:border-b-0"
            >
              <button
                type="button"
                onClick={() =>
                  void navigate({
                    to: "/settings/workflows",
                    search: { id: w.id },
                  })
                }
                className="w-full text-left px-4 py-3 hover:bg-bg-warm flex items-center justify-between"
              >
                <span className="text-[13.5px] text-ink">{w.name}</span>
                <span className="text-[11px] font-mono text-ink-faint">
                  v{w.version}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </SettingsLayout>
    );
  }

  const modes: Mode[] = [
    { id: "schema", label: "Schema" },
    { id: "overrides", label: "Overrides" },
    { id: "personas", label: "Personas" },
  ];

  return (
    <SettingsLayout
      title={selected.name}
      subtitle={`${selected.id} · v${selected.version}`}
    >
      <div className="-mt-2 -mx-6 mb-6 px-6 border-b-[0.5px] border-rule">
        <div role="tablist" className="flex gap-0 -mb-px">
          {modes.map((m) => {
            const isCurrent = m.id === mode;
            return (
              <button
                key={m.id}
                type="button"
                role="tab"
                aria-selected={isCurrent}
                onClick={() => setMode(m.id as WorkflowMode)}
                className={`px-4 pt-2.5 pb-3 text-[13px] border-b-[1.5px] ${
                  isCurrent
                    ? "text-ink border-navy font-medium"
                    : "text-ink-soft border-transparent hover:text-ink"
                }`}
              >
                {m.label}
              </button>
            );
          })}
        </div>
      </div>

      {mode === "schema" && <SchemaPane workflowId={selected.id} />}
      {mode === "overrides" && <OverridesPane workflowId={selected.id} />}
      {mode === "personas" && <PersonasPane workflowId={selected.id} />}
    </SettingsLayout>
  );
}

/* ─── Schema mode ─────────────────────────────────────────────────── */

function SchemaPane({ workflowId }: { workflowId: string }) {
  const navigate = useNavigate();
  return (
    <div className="space-y-4">
      <p className="text-[13px] text-ink-soft">
        The schema describes the data shape this workflow expects —
        every metric, alert, persona, decision type, and threshold
        declared in the workflow YAML.
      </p>
      <p className="text-[13px] text-ink-soft">
        The dedicated schema explorer (which lets you drill into every
        field) lives at its own URL for now.
      </p>
      <Button
        compact
        onClick={() =>
          void navigate({
            to: "/workflows/$workflowId/schema",
            params: { workflowId },
          })
        }
      >
        Open schema explorer →
      </Button>
    </div>
  );
}

/* ─── Overrides mode ──────────────────────────────────────────────── */

function OverridesPane({ workflowId }: { workflowId: string }) {
  const settings = useWorkflowSettings(workflowId);
  const history = useOverrideHistory(workflowId);
  const setOverride = useSetOverride();
  const supersede = useSupersedeOverride();

  if (settings.isLoading) {
    return <p className="text-body-sm text-ink-muted">Loading…</p>;
  }
  if (settings.isError || !settings.data) {
    return (
      <p className="text-body-sm text-critical-text">
        Couldn't load workflow config.
      </p>
    );
  }

  const overridable = Object.entries(settings.data.overridable_keys);
  const merged = settings.data.config as Record<string, unknown>;

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-3">
        <span className="text-[10px] tracking-[0.08em] uppercase text-ink-faint">
          Override mechanics
        </span>
        <HelpLink
          topic="settings/threshold-overrides"
          label="How do overrides work?"
        />
      </div>

      <section>
        <h3 className="mb-3 text-[11px] tracking-[0.08em] uppercase text-ink-soft font-medium">
          Overridable thresholds
        </h3>
        <div className="space-y-2">
          {overridable.map(([key, type]) => (
            <OverrideRow
              key={key}
              workflowId={workflowId}
              configKey={key}
              type={type}
              currentValue={resolveDotPath(merged, key)}
              onSet={(value, note) =>
                setOverride.mutate({
                  workflowId,
                  body: {
                    config_key: key,
                    config_value: value,
                    change_note: note,
                  },
                })
              }
              onClear={() =>
                supersede.mutate({ workflowId, configKey: key })
              }
              isPending={setOverride.isPending || supersede.isPending}
            />
          ))}
        </div>
      </section>

      <section>
        <h3 className="mb-3 text-[11px] tracking-[0.08em] uppercase text-ink-soft font-medium">
          Override history
        </h3>
        {history.data?.items.length ? (
          <ul className="space-y-2 text-body-sm">
            {history.data.items.map((row) => (
              <li
                key={row.id}
                className="flex flex-wrap items-baseline gap-2 border-t-[0.5px] border-rule-soft py-2"
              >
                <span className="font-mono text-[11px] text-ink-faint">
                  {row.modified_at
                    ? new Date(row.modified_at).toLocaleString()
                    : "—"}
                </span>
                <span className="font-mono text-[11px]">{row.config_key}</span>
                <span>= {JSON.stringify(row.config_value)}</span>
                {row.superseded_at && (
                  <span className="text-ink-faint">superseded</span>
                )}
                {row.change_note && (
                  <span className="text-ink-soft">— {row.change_note}</span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-body-sm text-ink-muted">
            No overrides recorded.
          </p>
        )}
      </section>
    </div>
  );
}

function OverrideRow({
  configKey,
  type,
  currentValue,
  onSet,
  onClear,
  isPending,
}: {
  workflowId: string;
  configKey: string;
  type: string;
  currentValue: unknown;
  onSet: (value: unknown, note?: string) => void;
  onClear: () => void;
  isPending: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>(
    currentValue !== undefined && currentValue !== null
      ? String(currentValue)
      : "",
  );
  const [note, setNote] = useState("");

  const submit = () => {
    const parsed =
      type === "int"
        ? parseInt(draft, 10)
        : type === "float"
          ? parseFloat(draft)
          : type === "bool"
            ? draft === "true"
            : type === "list" || type === "dict"
              ? safeJsonParse(draft)
              : draft;
    onSet(parsed, note || undefined);
    setEditing(false);
  };

  return (
    <div className="grid grid-cols-[1fr_120px_120px_auto] items-center gap-3 rounded-md border-[0.5px] border-rule-soft bg-paper px-3 py-2">
      <span className="font-mono text-[11px] text-ink">{configKey}</span>
      <span className="font-mono text-[11px] text-ink-faint">{type}</span>
      {editing ? (
        <div className="col-span-2 grid grid-cols-[1fr_1fr_auto_auto] gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="rounded-sm border-[0.5px] border-rule-soft bg-paper px-2 py-1 text-body-sm font-mono"
          />
          <input
            placeholder="reason / change note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="rounded-sm border-[0.5px] border-rule-soft bg-paper px-2 py-1 text-body-sm"
          />
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="text-body-sm text-ink-muted"
          >
            Cancel
          </button>
          <Button onClick={submit} disabled={isPending}>
            {isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      ) : (
        <>
          <span className="font-mono text-[11px] text-ink">
            {currentValue !== undefined && currentValue !== null
              ? JSON.stringify(currentValue)
              : "—"}
          </span>
          <div className="flex items-center gap-2 justify-self-end">
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-body-sm text-navy hover:underline"
            >
              Edit
            </button>
            <button
              type="button"
              onClick={onClear}
              disabled={isPending}
              className="text-body-sm text-ink-muted hover:text-critical-text"
            >
              Reset
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/* ─── Personas mode (stub) ────────────────────────────────────────── */

function PersonasPane({ workflowId }: { workflowId: string }) {
  void workflowId;
  return (
    <div className="space-y-4">
      <p className="text-[13px] text-ink-soft">
        Personas declare who watches what — which decision types,
        signals, and reports each role on this workflow attends to.
        Defined in the workflow YAML; tenant overrides land here.
      </p>
      <p className="text-[12px] font-mono uppercase tracking-[0.06em] text-ink-faint">
        Persona editor wires in a follow-up commit.
      </p>
    </div>
  );
}

/* ─── Helpers ─────────────────────────────────────────────────────── */

function resolveDotPath(obj: unknown, path: string): unknown {
  return path
    .split(".")
    .reduce<unknown>(
      (acc, part) =>
        acc && typeof acc === "object" && part in (acc as object)
          ? (acc as Record<string, unknown>)[part]
          : undefined,
      obj,
    );
}

function safeJsonParse(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}
