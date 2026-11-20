# TwinLedger Accounting Rules (normative, Phase 1 skeleton)

Status: normative specification shared by generator and verifier
(TZ 3, 12). Implementations must not share detection code — only this
specification and `contracts/`.

## 1. Money
- All stored amounts are integer minor units (REQ-MONEY-001).
- Decimal is created from strings only (REQ-MONEY-002).
- Rounding mode comes from `policy.json` (`half_even` / `half_up`).

## 2. FX policy
- Rate date rule, fallback rule, source codes and quote convention are
  declared in `policy.json` (`fx_policy`).
- The *selection* algorithm (which rate row applies) is implemented
  independently in generator and verifier (TZ 9.3). Only the low-level
  money conversion helper may be shared, and it is covered by
  hand-authored reference vectors (Phase 2).

## 3. Period cutoff
- Recognition event and timezone source are declared in `policy.json`
  (`cutoff_policy`). Period is computed in the company timezone
  (REQ-TIME-002).

## 4. Allocation
- Allocation rules (advances, multi-invoice splits) are declared in
  `policy.json` (`allocation_policy`).

## 5. Anomaly semantics
See `spec/anomaly_catalog.yaml` for the four types, affected-ID rules
and distractor pairs. Text is supplemental evidence only (REQ-NLP-002).
