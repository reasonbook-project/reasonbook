// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Glossary — single source of truth for term definitions surfaced
 * via the HelpTerm / Tooltip primitives.
 *
 * Each term has a short plain-English definition and an optional
 * concrete example. The HelpTerm component looks the term up by key
 * and renders the popover. Keep entries terse — these are airport-
 * signage definitions, not encyclopedia entries.
 *
 * Adding a term: pick a short kebab-case key, add the entry, then
 * wrap the term in JSX with <HelpTerm term="kebab-key">label</HelpTerm>.
 */

export type GlossaryTerm = {
  /** The label as it usually appears in UI. */
  label: string;
  /** One- to two-sentence definition in plain English. */
  definition: string;
  /** Optional concrete example to anchor the definition. */
  example?: string;
};

export const glossary = {
  matter: {
    label: "Matter",
    definition:
      "A federal funding line tracked end-to-end: the originating award, every downstream tier (state, recipient, subrecipient), and every decision made along the way.",
    example: "An NIH-R01 grant from HHS to State U with a subaward to a county lab.",
  },

  archetype: {
    label: "Playbook",
    definition:
      "The playbook this matter follows — the declared kind of funding decision, with its stages, gates, and required evidence. Officers act within a playbook rather than inventing process case by case.",
    example:
      "Competitive award (NIH-R01), formula allocation (CDBG), payment authorization (Treasury disbursement), identity resolution (dispute adjudication).",
  },

  "tier-skip": {
    label: "Tier-skip",
    definition:
      "A flow anomaly where money moved from one tier directly to a deeper tier, bypassing an expected pass-through.",
    example:
      "USDA paying a local sponsor directly without the state agency in the middle.",
  },

  "control-point": {
    label: "Control point",
    definition:
      "A checkpoint federal law or agency policy says must happen before money moves. Each can be cleared, marked as a named gap with a reason, or recorded as missed.",
    example: "Eligibility check, conflict-of-interest review, budget sign-off.",
  },

  "hash-chain": {
    label: "Hash chain",
    definition:
      "A cryptographic chain of every event on a matter. Each new event hashes the previous event's hash, so any tampering after the fact is detectable.",
    example:
      "Same primitive as Git or Bitcoin uses — SHA-256, applied to decision events.",
  },

  signal: {
    label: "Signal",
    definition:
      "A flag raised against a matter by a detection source. Not a decision by itself — every signal requires a human disposition (promote, dismiss, hold) with a written reason.",
    example: "Phantom subrecipient, identity-match failure, recipient-tier address mismatch.",
  },

  disposition: {
    label: "Disposition",
    definition:
      "The human decision on a signal: promote (becomes a Decision), dismiss (with reason), hold (more info needed), or reopen.",
  },

  "named-gap": {
    label: "Named gap",
    definition:
      "A control point that was skipped, with a written reason on the record. Skipping silently is not allowed — every gap must be named.",
  },

  rfr: {
    label: "RFR",
    definition:
      "Request For Response — the record of a federal PM asking an external party to answer a specific question about a matter. Carries a prompt type, prompt body, target party, and due date. When the party responds, the RFR is superseded by a commitment.",
    example:
      "Accept the scope of work as issued (RFR-2026-04-2118, due in 5 days, to Stanford University).",
  },

  commitment: {
    label: "Commitment",
    definition:
      "An external party's structured response to an RFR, captured as an append-only Decision (is_commitment=true) on the target matter. Legally binding evidence — supersedes the open RFR row on the case file.",
    example:
      "Stanford accepted the scope as issued, signed by Dr. Ellen Weiss (AVP Research), via Login.gov IAL2/AAL2 MFA.",
  },

  "commitment-attestation": {
    label: "Commitment attestation",
    definition:
      "The two required assertions a party signs when submitting a commitment: 'authorized to bind' (I speak for this party) and 'understands commitment' (I know this response is on the record). Both are enforced server-side; a response missing either is rejected.",
  },

  party: {
    label: "Party",
    definition:
      "A distinct external entity that can hold entitlements on a matter — a state pass-through agency, a recipient organization, a subrecipient. Parties respond to RFRs and their responses are recorded as commitments against the matter.",
    example: "Stanford University, California Department of Social Services, Delta CDC.",
  },

  inbox: {
    label: "Inbox",
    definition:
      "The decision queue. Scoped to Mine, Team, or All agency. Stage-tagged by what's next: awaiting decision, awaiting action, awaiting committee, awaiting outcome, recently decided. In Mine scope, the labels read 'awaiting my decision' etc. to name who owes the next step.",
  },

  scope: {
    label: "Scope",
    definition:
      "Filter that controls which decisions you see in the Inbox: Mine (only what's claimed by you), Team (your supervisees), All agency (everything your agency owns).",
  },

  tier: {
    label: "Tier",
    definition:
      "A position in the federal fund-flow chain. Federal at the top, then state pass-through, then recipient, then subrecipient.",
  },

  workflow: {
    label: "Workflow",
    definition:
      "A program-specific pipeline that binds a playbook to a real program. Defines roles, gates, evidence, and authority levels.",
    example: "NIH-R01, CDBG, Treasury disbursement.",
  },

  authority: {
    label: "Authority",
    definition:
      "A user's level of decision-making power on a specific workflow. Granted, append-only, with limits captured at grant time.",
  },

  finding: {
    label: "Finding",
    definition:
      "A formal observation by oversight: something on a matter that doesn't meet policy, regulation, or process requirements.",
  },

  "verify-chain": {
    label: "Verify chain",
    definition:
      "Recompute the hash chain from the beginning and confirm the current head matches. If any event was modified after the fact, the chain returns broken.",
  },

  "case-file": {
    label: "Case file",
    definition:
      "The forensic long-form view of a matter: cover, fund flow, signals, decisions, process adherence, audit chain. Print-ready, OIG-suitable.",
  },
} as const satisfies Record<string, GlossaryTerm>;

export type GlossaryKey = keyof typeof glossary;
