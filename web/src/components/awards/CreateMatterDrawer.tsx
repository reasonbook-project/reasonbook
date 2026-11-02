// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";

import { Button } from "@/components/ds/Button";
import {
  useAgencies,
  useCreateMatter,
  useParticipantOrgs,
} from "@/hooks/useMatters";
import { usePrograms } from "@/hooks/usePrograms";

type Props = {
  open: boolean;
  onClose: () => void;
  onCreated?: (matterId: string) => void;
};

type StateEntry = { participant_org_id: string };
type RecipientEntry = {
  parent_state_org_id: string;
  participant_org_id: string;
};

/**
 * Create-matter drawer — TENANCY-MODEL §10 step 8 part 3, §12.
 *
 * Federal-tier only. Submits to POST /api/matters via
 * dp/matters/service::create_matter.
 *
 * Visual is intentionally minimal so the data path is clear and
 * testable. A later pass can polish the layout against
 * docs/architecture/UI/new-award-matter.html.
 */
export function CreateMatterDrawer({ open, onClose, onCreated }: Props) {
  const programs = usePrograms();
  const states = useParticipantOrgs("state");
  const recipients = useParticipantOrgs("recipient");
  const agencies = useAgencies();
  const create = useCreateMatter();

  const [programId, setProgramId] = useState("");
  const [awardingAgency, setAwardingAgency] = useState("");
  const [amount, setAmount] = useState("");
  const [period, setPeriod] = useState("FY26");
  const [terms, setTerms] = useState("");
  const [appRef, setAppRef] = useState("");
  const [selectedStates, setSelectedStates] = useState<StateEntry[]>([]);
  const [selectedRecipients, setSelectedRecipients] = useState<RecipientEntry[]>(
    [],
  );

  if (!open) return null;

  function reset() {
    setProgramId("");
    setAwardingAgency("");
    setAmount("");
    setPeriod("FY26");
    setTerms("");
    setAppRef("");
    setSelectedStates([]);
    setSelectedRecipients([]);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const result = await create.mutateAsync({
      program_id: programId,
      awarding_agency: awardingAgency,
      amount_obligated: amount,
      period_label: period,
      terms,
      federal_application_ref: appRef,
      states: selectedStates,
      recipients: selectedRecipients,
    });
    reset();
    onClose();
    onCreated?.(result.id);
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close drawer"
        className="absolute inset-0 bg-black/20"
        onClick={onClose}
      />
      <form
        onSubmit={submit}
        className="relative z-10 flex h-full w-full max-w-[560px] flex-col overflow-y-auto border-l-[0.5px] border-rule bg-paper-warm"
      >
        <header className="border-b-[0.5px] border-rule-soft px-6 py-4">
          <h2 className="text-h3 font-medium text-brand-ink">
            Create award matter
          </h2>
          <p className="mt-1 text-body-sm text-ink-soft">
            Federal-tier only · idempotent on
            (program · agency · period · application ref)
          </p>
        </header>

        <div className="flex-1 space-y-5 px-6 py-5">
          <Field label="Program" required>
            <select
              required
              value={programId}
              onChange={(e) => setProgramId(e.target.value)}
              className="w-full rounded-sm border-[0.5px] border-rule-soft bg-white px-3 py-2 text-body"
            >
              <option value="">Select a program…</option>
              {(programs.data?.programs ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name ?? p.name} ({p.id})
                </option>
              ))}
            </select>
          </Field>

          <Field label="Awarding agency" required>
            <input
              type="text"
              required
              list="awarding-agency-options"
              value={awardingAgency}
              onChange={(e) => setAwardingAgency(e.target.value)}
              placeholder="Start typing — e.g. HUD, NIH, USDA"
              autoComplete="off"
              className="w-full rounded-sm border-[0.5px] border-rule-soft bg-white px-3 py-2 text-body"
            />
            <datalist id="awarding-agency-options">
              {(agencies.data?.agencies ?? []).map((a) => (
                <option key={a.id} value={a.display_name} />
              ))}
            </datalist>
            <p className="mt-1 text-[12px] text-ink-muted">
              Suggestions sourced from the federal agency catalog
              (USAspending pull · {agencies.data?.count ?? 0} agencies).
              Free-form input is accepted for agencies not yet catalogued.
            </p>
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="Amount obligated" required>
              <input
                type="text"
                required
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="12000000.00"
                className="w-full rounded-sm border-[0.5px] border-rule-soft bg-white px-3 py-2 text-body"
              />
            </Field>
            <Field label="Period" required>
              <input
                type="text"
                required
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                className="w-full rounded-sm border-[0.5px] border-rule-soft bg-white px-3 py-2 text-body"
              />
            </Field>
          </div>

          <Field label="Terms" required>
            <textarea
              required
              rows={2}
              value={terms}
              onChange={(e) => setTerms(e.target.value)}
              placeholder="FY26 · Uniform Guidance 2 CFR 200 · 60-month retention"
              className="w-full rounded-sm border-[0.5px] border-rule-soft bg-white px-3 py-2 text-body"
            />
          </Field>

          <Field label="Federal application ref" required>
            <input
              type="text"
              required
              value={appRef}
              onChange={(e) => setAppRef(e.target.value)}
              placeholder="HUD-CDBG-2026-001"
              className="w-full rounded-sm border-[0.5px] border-rule-soft bg-white px-3 py-2 text-body"
            />
            <p className="mt-1 text-[12px] text-ink-muted">
              Hashed with program/agency/period for the idempotency key —
              same tuple → same matter id, replays are no-ops.
            </p>
          </Field>

          <StakeholderSection
            label="State stakeholders"
            options={states.data?.items ?? []}
            selected={selectedStates}
            onAdd={(orgId) =>
              setSelectedStates((prev) =>
                prev.some((s) => s.participant_org_id === orgId)
                  ? prev
                  : [...prev, { participant_org_id: orgId }],
              )
            }
            onRemove={(orgId) =>
              setSelectedStates((prev) =>
                prev.filter((s) => s.participant_org_id !== orgId),
              )
            }
          />

          <RecipientSection
            states={selectedStates}
            stateLookup={new Map(
              (states.data?.items ?? []).map((s) => [s.id, s.display_name]),
            )}
            options={recipients.data?.items ?? []}
            selected={selectedRecipients}
            onAdd={(entry) =>
              setSelectedRecipients((prev) =>
                prev.some(
                  (r) =>
                    r.parent_state_org_id === entry.parent_state_org_id &&
                    r.participant_org_id === entry.participant_org_id,
                )
                  ? prev
                  : [...prev, entry],
              )
            }
            onRemove={(entry) =>
              setSelectedRecipients((prev) =>
                prev.filter(
                  (r) =>
                    !(
                      r.parent_state_org_id === entry.parent_state_org_id &&
                      r.participant_org_id === entry.participant_org_id
                    ),
                ),
              )
            }
          />

          {create.isError && (
            <div className="rounded-sm bg-critical/5 px-3 py-2 text-body-sm text-critical-text">
              {(create.error as Error).message}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-end gap-3 border-t-[0.5px] border-rule-soft px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="text-body-sm text-ink-soft hover:underline"
            disabled={create.isPending}
          >
            Cancel
          </button>
          <Button type="submit" disabled={create.isPending || !programId}>
            {create.isPending ? "Creating…" : "Create matter"}
          </Button>
        </footer>
      </form>
    </div>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] font-medium text-ink-soft">
        {label}
        {required && <span className="ml-0.5 text-critical-text">*</span>}
      </span>
      {children}
    </label>
  );
}

type ParticipantOrgOption = {
  id: string;
  display_name: string;
  code: string | null;
};

function StakeholderSection({
  label,
  options,
  selected,
  onAdd,
  onRemove,
}: {
  label: string;
  options: ParticipantOrgOption[];
  selected: StateEntry[];
  onAdd: (orgId: string) => void;
  onRemove: (orgId: string) => void;
}) {
  const [picker, setPicker] = useState("");
  return (
    <div>
      <div className="mb-1 text-[12px] font-medium text-ink-soft">{label}</div>
      <div className="space-y-1">
        {selected.length === 0 && (
          <div className="rounded-sm border-[0.5px] border-dashed border-rule-faint px-3 py-2 text-body-sm italic text-ink-muted">
            None yet — add states via the picker below.
          </div>
        )}
        {selected.map((s) => {
          const o = options.find((x) => x.id === s.participant_org_id);
          return (
            <div
              key={s.participant_org_id}
              className="flex items-center justify-between rounded-sm border-[0.5px] border-rule-faint px-3 py-2"
            >
              <span className="text-body">
                {o ? o.display_name : s.participant_org_id}
              </span>
              <button
                type="button"
                onClick={() => onRemove(s.participant_org_id)}
                className="text-body-sm text-critical-text hover:underline"
              >
                Remove
              </button>
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <select
          value={picker}
          onChange={(e) => setPicker(e.target.value)}
          className="flex-1 rounded-sm border-[0.5px] border-rule-soft bg-white px-3 py-2 text-body-sm"
        >
          <option value="">Add a state…</option>
          {options
            .filter(
              (o) => !selected.some((s) => s.participant_org_id === o.id),
            )
            .map((o) => (
              <option key={o.id} value={o.id}>
                {o.display_name}
              </option>
            ))}
        </select>
        <button
          type="button"
          disabled={!picker}
          onClick={() => {
            if (picker) onAdd(picker);
            setPicker("");
          }}
          className="rounded-sm border-[0.5px] border-rule-soft px-3 py-2 text-body-sm hover:bg-ink/[0.04] disabled:opacity-50"
        >
          Add
        </button>
      </div>
    </div>
  );
}

function RecipientSection({
  states,
  stateLookup,
  options,
  selected,
  onAdd,
  onRemove,
}: {
  states: StateEntry[];
  stateLookup: Map<string, string>;
  options: ParticipantOrgOption[];
  selected: RecipientEntry[];
  onAdd: (entry: RecipientEntry) => void;
  onRemove: (entry: RecipientEntry) => void;
}) {
  const [parent, setParent] = useState("");
  const [recip, setRecip] = useState("");
  return (
    <div>
      <div className="mb-1 text-[12px] font-medium text-ink-soft">
        Recipients
      </div>
      {states.length === 0 ? (
        <div className="rounded-sm border-[0.5px] border-dashed border-rule-faint px-3 py-2 text-body-sm italic text-ink-muted">
          Add states first; recipients hang off a parent state.
        </div>
      ) : (
        <>
          <div className="space-y-1">
            {selected.length === 0 && (
              <div className="rounded-sm border-[0.5px] border-dashed border-rule-faint px-3 py-2 text-body-sm italic text-ink-muted">
                No recipients yet.
              </div>
            )}
            {selected.map((r) => {
              const o = options.find((x) => x.id === r.participant_org_id);
              return (
                <div
                  key={`${r.parent_state_org_id}-${r.participant_org_id}`}
                  className="flex items-center justify-between rounded-sm border-[0.5px] border-rule-faint px-3 py-2"
                >
                  <span className="text-body">
                    {o ? o.display_name : r.participant_org_id}
                    <span className="ml-2 text-body-sm text-ink-muted">
                      under {stateLookup.get(r.parent_state_org_id) ?? "—"}
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() => onRemove(r)}
                    className="text-body-sm text-critical-text hover:underline"
                  >
                    Remove
                  </button>
                </div>
              );
            })}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <select
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              className="rounded-sm border-[0.5px] border-rule-soft bg-white px-3 py-2 text-body-sm"
            >
              <option value="">Parent state…</option>
              {states.map((s) => (
                <option key={s.participant_org_id} value={s.participant_org_id}>
                  {stateLookup.get(s.participant_org_id) ?? s.participant_org_id}
                </option>
              ))}
            </select>
            <select
              value={recip}
              onChange={(e) => setRecip(e.target.value)}
              className="flex-1 rounded-sm border-[0.5px] border-rule-soft bg-white px-3 py-2 text-body-sm"
            >
              <option value="">Recipient…</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.display_name}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={!parent || !recip}
              onClick={() => {
                onAdd({ parent_state_org_id: parent, participant_org_id: recip });
                setParent("");
                setRecip("");
              }}
              className="rounded-sm border-[0.5px] border-rule-soft px-3 py-2 text-body-sm hover:bg-ink/[0.04] disabled:opacity-50"
            >
              Add
            </button>
          </div>
        </>
      )}
    </div>
  );
}
