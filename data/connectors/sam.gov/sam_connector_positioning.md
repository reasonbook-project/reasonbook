# SAM.gov Connector — Scope & Positioning

**Status:** Prototype
**Role in DP:** Corroborating risk signal, not a primary decision driver

---

## What it is

A narrow connector that turns a UEI into one radar blip: *is this entity
registered, active, and not debarred?* Nothing more.

It sits alongside the other federal sources on the risk-signals radar
(SAM, LEIE, DMF, Treasury Do Not Pay, USAspending) and feeds the same
air-traffic-controller view.

## Why interest is deliberately limited

- **SAM is a verification layer, not a discovery source.** It confirms an
  entity's federal standing. It doesn't surface new risk on its own the way
  exclusion or death-record matches do.
- **The signal is binary and low-churn.** Registration status and exclusion
  flags change slowly. This is a periodic check, not a live feed.
- **Overlap with stronger signals.** Debarment shows up here, but the
  authoritative debarment detail and adjacent lists carry more weight in a
  verdict. SAM mostly *confirms* what other blips already suggest.
- **Access is throttled.** The individual key is capped (~1,000 req/day).
  That's fine for a corroborating check; it rules SAM out as a high-volume
  primary source without a system account (1–4 wk approval + static IP).

## What it does

- `get_signal(uei)` → normalized `RiskSignal`
- Severity: `clear` / `caution` / `alert` / `unknown`
- Fails soft — a SAM outage returns an `unknown` blip, never crashes the sweep

## What it does *not* do

- No opportunities / solicitation data (not DP's use case)
- No name-only fuzzy screening as a primary path (UEI is the key)
- No write-back — SAM is read-only public data

## Effort profile

| Item | Cost |
|---|---|
| Prototype (this) | Done — individual key, one module |
| Production volume | Higher — system account, static egress IP on DO |
| Ongoing maintenance | Low — stable endpoints, slow-changing data |

## Next steps (if promoted past prototype)

1. Align `RiskSignal` fields with DP's real signal contract
2. Add a nightly cache (SAM data updates daily — no need for live calls)
3. Decide if volume justifies the system-account path
