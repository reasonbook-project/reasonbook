// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, useNavigate, useParams } from "@tanstack/react-router";
import { format } from "date-fns";
import { useEffect, useMemo, useState } from "react";

import type {
  RecipientResponseInput,
  RecipientResponseShape,
} from "@/api/matters";
import { Button } from "@/components/ds/Button";
import { DetailContainer } from "@/components/ds/DetailContainer";
import { EmptyState } from "@/components/ds/EmptyState";
import { SkeletonRows } from "@/components/ds/Skeleton";
import { AppShellV2 } from "@/components/shell/AppShellV2";
import { useMatter, useSubmitRecipientResponse } from "@/hooks/useMatters";
import { useAuthStore } from "@/stores/auth";
import { cn } from "@/lib/cn";

import { rootRoute } from "./__root";
import { PreviewCommitmentModal } from "@/components/decision/PreviewCommitmentModal";

/**
 * Recipient response form (MVP-slice, backlog A0).
 * Path: /matters/$matterId/response
 *
 * Five bands per docs/demo/external-party-response-scaffolding.md:
 *   1 · Context strip     (award / from / to / due / RFR ref)
 *   2 · The prompt        (federal-authored, read-only)
 *   3 · Structured input  (accepted / exceptions / signatory)
 *   4 · Attestation       (two required checkboxes + IdP session pill)
 *   5 · Actions           (preview / submit)
 *
 * A0 note (code, not UI): the caller is authenticated internally and
 * submits AS-IF a recipient. The session pill in Band 4 reads
 * "Login.gov · IAL2/AAL2" as demo-realistic copy — real Login.gov
 * OAuth + invite-MFA lands with Phase B (spec §3.3, §8). Party legal
 * name is a form field until the `parties` table lands.
 */
export const recipientResponseRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/matters/$matterId/response",
  component: RecipientResponseForm,
});

const REQUIRED_ATTESTATIONS = [
  {
    id: "authorized_to_bind",
    label:
      "I am authorized to bind the responding party to the scope indicated above.",
  },
  {
    id: "understands_commitment",
    label:
      "I understand this response is a legally binding commitment recorded in the federal decision ledger, and that changes require formal supersession.",
  },
] as const;

function RecipientResponseForm() {
  const { matterId } = useParams({ from: recipientResponseRoute.id });
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);

  const matterQuery = useMatter(matterId);
  const submitMutation = useSubmitRecipientResponse(matterId);

  // Form state
  const [partyName, setPartyName] = useState("");
  const [partyNamePrefilledFrom, setPartyNamePrefilledFrom] = useState<
    string | null
  >(null);
  const [rfrRef, setRfrRef] = useState("");

  // Prefill party name from the matter's recipient node when the
  // matter loads. Only fills while the field is untouched — once the
  // user edits it, we back off so their input isn't clobbered on
  // background refetch. Real Phase B resolves party from the session
  // and the field goes away entirely.
  useEffect(() => {
    if (!matterQuery.data) return;
    if (partyName.trim().length > 0) return;
    const recipientNode = matterQuery.data.nodes.find(
      (n) => n.tier === "recipient" && n.participant_org_name,
    );
    if (!recipientNode?.participant_org_name) return;
    setPartyName(recipientNode.participant_org_name);
    setPartyNamePrefilledFrom(recipientNode.participant_org_name);
  }, [matterQuery.data, partyName]);
  const [accepted, setAccepted] =
    useState<RecipientResponseShape["accepted"]>("as_issued");
  const [exceptions, setExceptions] = useState("");
  const [signatoryName, setSignatoryName] = useState(user?.name ?? "");
  const [signatoryTitle, setSignatoryTitle] = useState("");
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [previewOpen, setPreviewOpen] = useState(false);

  const allAttestationsChecked = REQUIRED_ATTESTATIONS.every(
    (a) => checked[a.id],
  );
  const requiredFieldsFilled =
    partyName.trim().length > 0 &&
    signatoryName.trim().length > 0 &&
    signatoryTitle.trim().length > 0;
  const canSubmit =
    allAttestationsChecked && requiredFieldsFilled && !submitMutation.isPending;

  const responseShape: RecipientResponseShape = useMemo(
    () => ({
      prompt_type: "accept_scope",
      accepted,
      exceptions: accepted === "with_exceptions" ? exceptions.trim() : null,
      signatory_name: signatoryName.trim(),
      signatory_title: signatoryTitle.trim(),
      attestations: REQUIRED_ATTESTATIONS.filter((a) => checked[a.id]).map(
        (a) => a.id,
      ),
      attachments: [],
    }),
    [accepted, exceptions, signatoryName, signatoryTitle, checked],
  );

  const submit = () => {
    if (!canSubmit) return;
    const input: RecipientResponseInput = {
      originating_party_name: partyName.trim(),
      in_response_to: rfrRef.trim() || null,
      response_shape: responseShape,
    };
    submitMutation.mutate(input, {
      onSuccess: () => {
        void navigate({
          to: "/matters",
          search: { id: matterId, mode: "case-file" },
        });
      },
    });
  };

  return (
    <AppShellV2>
      {/* AppShellV2's main is a row flexbox; centering with justify-center
          + a bounded max-width child keeps DetailContainer's internal
          overflow-y-auto working correctly. Wrapping the DetailContainer
          in its own overflow-y-auto here would double-scroll. */}
      <div className="flex flex-1 justify-center overflow-hidden min-h-0">
        <div className="flex w-full max-w-[820px] flex-col min-h-0">
          <DetailContainer
            title="Respond to scope of work"
            subtitle="Federal-proxy path · demo A0"
          >
            <div className="space-y-5 px-6 py-6">
            {matterQuery.isLoading && <SkeletonRows />}
            {matterQuery.isError && (
              <EmptyState
                headline="We couldn't load the matter."
                body={<>Refresh to try again.</>}
              />
            )}
            {matterQuery.isSuccess && matterQuery.data && (
              <>
                {/* ── Band 1 · Context strip ─────────────────────── */}
                <FormBand label="Context">
                  <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-[13px]">
                    <ContextRow label="Award">
                      <span className="font-mono text-[12px]">
                        {matterQuery.data.program_id.toUpperCase()} ·{" "}
                        {matterQuery.data.awarding_agency}
                      </span>
                    </ContextRow>
                    <ContextRow label="Recipient (as of party field)">
                      {partyName || (
                        <span className="text-ink-faint italic">
                          Enter party legal name below
                        </span>
                      )}
                    </ContextRow>
                    <ContextRow label="Period">
                      {matterQuery.data.period_label ?? "—"}
                    </ContextRow>
                    <ContextRow label="RFR reference">
                      <span className="font-mono text-[12px]">
                        {rfrRef || (
                          <span className="text-ink-faint italic">
                            optional
                          </span>
                        )}
                      </span>
                    </ContextRow>
                    <ContextRow label="Date">
                      {format(new Date(), "d MMM yyyy")}
                    </ContextRow>
                    <ContextRow label="Submitted by">
                      {user?.name ?? user?.username ?? "—"} (federal proxy)
                    </ContextRow>
                  </div>
                </FormBand>

                {/* ── Band 2 · The prompt ─────────────────────────── */}
                <FormBand label="Prompt" readOnly>
                  <div className="text-[13px] leading-relaxed text-ink">
                    <strong className="font-display font-medium">
                      Accept the scope of work as issued.
                    </strong>
                    <p className="mt-2 text-ink-soft">
                      This response will be captured as an append-only Decision
                      in the federal ledger, tagged as a legally-binding
                      commitment. The federal PM will see the response arrive
                      on their matter timeline.
                    </p>
                  </div>
                </FormBand>

                {/* ── Band 3 · Structured response ────────────────── */}
                <FormBand label="Response">
                  <div className="space-y-4">
                    <div>
                      <TextField
                        label="Responding party legal name"
                        value={partyName}
                        onChange={setPartyName}
                        placeholder="e.g. Stanford University"
                        required
                      />
                      {partyNamePrefilledFrom &&
                        partyName === partyNamePrefilledFrom && (
                          <p className="mt-1 text-[11px] text-ink-faint italic">
                            Prefilled from this matter's recipient node ·
                            editable for the A0 demo (Phase B resolves party
                            from the session).
                          </p>
                        )}
                    </div>
                    <TextField
                      label="RFR reference (optional)"
                      value={rfrRef}
                      onChange={setRfrRef}
                      placeholder="RFR-2026-04-2118"
                      mono
                    />

                    <div>
                      <label className="mb-2 block font-display text-[12px] font-medium tracking-wider text-ink-soft uppercase">
                        Do you accept the scope as issued?
                      </label>
                      <div className="flex flex-col gap-2">
                        <RadioOption
                          label="Accept as issued"
                          value="as_issued"
                          selected={accepted === "as_issued"}
                          onSelect={setAccepted}
                        />
                        <RadioOption
                          label="Accept with noted exceptions"
                          value="with_exceptions"
                          selected={accepted === "with_exceptions"}
                          onSelect={setAccepted}
                        />
                        <RadioOption
                          label="Decline"
                          value="declined"
                          selected={accepted === "declined"}
                          onSelect={setAccepted}
                        />
                      </div>
                    </div>

                    {accepted === "with_exceptions" && (
                      <div>
                        <label className="mb-1 block font-display text-[12px] font-medium tracking-wider text-ink-soft uppercase">
                          Exceptions or clarifications
                        </label>
                        <textarea
                          value={exceptions}
                          onChange={(e) => setExceptions(e.target.value)}
                          className="w-full rounded-md border-[0.5px] border-rule bg-paper p-3 text-[13px] focus:border-navy focus:outline-none"
                          rows={4}
                          placeholder="Describe the exceptions the responding party is asserting."
                        />
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-3">
                      <TextField
                        label="Authorized signatory name"
                        value={signatoryName}
                        onChange={setSignatoryName}
                        required
                      />
                      <TextField
                        label="Signatory title"
                        value={signatoryTitle}
                        onChange={setSignatoryTitle}
                        placeholder="e.g. Associate VP, Research"
                        required
                      />
                    </div>
                  </div>
                </FormBand>

                {/* ── Band 4 · Attestation ────────────────────────── */}
                <FormBand label="Commitment attestation" accent>
                  <div className="space-y-2">
                    {REQUIRED_ATTESTATIONS.map((a) => (
                      <Attestation
                        key={a.id}
                        label={a.label}
                        checked={!!checked[a.id]}
                        onToggle={() =>
                          setChecked((prev) => ({
                            ...prev,
                            [a.id]: !prev[a.id],
                          }))
                        }
                      />
                    ))}
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-4 rounded-md border-[0.5px] border-rule-soft bg-bg-warm px-3 py-2 text-[12px] text-ink-soft">
                    <span className="inline-flex items-center gap-1.5">
                      <i
                        className="ti ti-shield-check text-[14px] text-ok"
                        aria-hidden
                      />
                      Login.gov · IAL2/AAL2 · MFA active
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <i
                        className="ti ti-clock text-[14px] text-ok"
                        aria-hidden
                      />
                      Timestamped on submit · SHA-256 chain-anchored
                    </span>
                  </div>
                </FormBand>

                {/* ── Band 5 · Actions ────────────────────────────── */}
                <div className="flex items-center justify-between rounded-md border-[0.5px] border-rule bg-paper px-5 py-4">
                  <div className="text-[12px] text-ink-muted">
                    {!allAttestationsChecked && (
                      <>Both attestations required to submit.</>
                    )}
                    {allAttestationsChecked && !requiredFieldsFilled && (
                      <>Fill party name and signatory fields to continue.</>
                    )}
                    {canSubmit && (
                      <span className="text-ok">Ready to submit.</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      onClick={() => setPreviewOpen(true)}
                      disabled={!requiredFieldsFilled}
                    >
                      Preview commitment
                    </Button>
                    <Button onClick={submit} disabled={!canSubmit}>
                      {submitMutation.isPending
                        ? "Submitting…"
                        : "Submit commitment"}
                    </Button>
                  </div>
                </div>

                {submitMutation.isError && (
                  <div className="rounded-md border-[0.5px] border-flag bg-flag-soft px-4 py-3 text-[13px] text-flag">
                    Submit failed. Check that both attestations are checked
                    and required fields are filled.
                  </div>
                )}

                <PreviewCommitmentModal
                  open={previewOpen}
                  onClose={() => setPreviewOpen(false)}
                  matter={matterQuery.data}
                  input={{
                    originating_party_name: partyName.trim(),
                    in_response_to: rfrRef.trim() || null,
                    response_shape: responseShape,
                  }}
                  onConfirm={() => {
                    setPreviewOpen(false);
                    submit();
                  }}
                  canConfirm={canSubmit}
                />
              </>
            )}
          </div>
          </DetailContainer>
        </div>
      </div>
    </AppShellV2>
  );
}

/* ─── Band shell ─────────────────────────────────────────────────────── */

function FormBand({
  label,
  children,
  readOnly,
  accent,
}: {
  label: string;
  children: React.ReactNode;
  readOnly?: boolean;
  accent?: boolean;
}) {
  return (
    <section
      className={cn(
        "rounded-md border-[0.5px] bg-paper",
        accent ? "border-navy/40" : "border-rule",
      )}
    >
      <div
        className={cn(
          "flex items-center gap-2 border-b-[0.5px] px-4 py-2",
          accent
            ? "border-navy/40 bg-navy-soft/20 text-navy"
            : "border-rule-soft text-ink-soft",
        )}
      >
        <span className="font-display text-[12px] font-medium tracking-wider uppercase">
          {label}
        </span>
        {readOnly && (
          <span className="font-mono text-[10px] text-ink-faint">
            read-only
          </span>
        )}
      </div>
      <div className="px-4 py-4">{children}</div>
    </section>
  );
}

function ContextRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <span className="text-ink-soft">{label}</span>
      <span className="text-ink">{children}</span>
    </>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  required,
  mono,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
  mono?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block font-display text-[12px] font-medium tracking-wider text-ink-soft uppercase">
        {label}
        {required && <span className="ml-1 text-flag">*</span>}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn(
          "h-9 w-full rounded-md border-[0.5px] border-rule bg-paper px-3 text-[13px] focus:border-navy focus:outline-none",
          mono && "font-mono text-[12px]",
        )}
      />
    </div>
  );
}

function RadioOption({
  label,
  value,
  selected,
  onSelect,
}: {
  label: string;
  value: RecipientResponseShape["accepted"];
  selected: boolean;
  onSelect: (v: RecipientResponseShape["accepted"]) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(value)}
      className={cn(
        "flex items-center gap-3 rounded-md border-[0.5px] px-4 py-2.5 text-left text-[13px] transition-colors",
        selected
          ? "border-ok bg-ok-soft text-ink"
          : "border-rule bg-paper text-ink-soft hover:border-rule-soft",
      )}
      aria-pressed={selected}
    >
      <span
        className={cn(
          "flex h-3.5 w-3.5 items-center justify-center rounded-full border-[0.5px]",
          selected ? "border-ok bg-ok" : "border-rule",
        )}
      >
        {selected && (
          <span className="h-1.5 w-1.5 rounded-full bg-white" aria-hidden />
        )}
      </span>
      {label}
    </button>
  );
}

function Attestation({
  label,
  checked,
  onToggle,
}: {
  label: string;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "flex w-full items-start gap-3 rounded-md border-[0.5px] px-3 py-2.5 text-left text-[13px]",
        checked ? "border-ok bg-ok-soft" : "border-rule bg-paper",
      )}
      aria-pressed={checked}
    >
      <span
        className={cn(
          "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border-[0.5px]",
          checked ? "border-ok bg-ok text-white" : "border-rule bg-paper",
        )}
      >
        {checked && <i className="ti ti-check text-[12px]" aria-hidden />}
      </span>
      <span className="text-ink">{label}</span>
    </button>
  );
}
