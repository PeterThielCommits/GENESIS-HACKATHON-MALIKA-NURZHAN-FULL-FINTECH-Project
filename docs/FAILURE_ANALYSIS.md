# Measured Failure Analysis & Re-Verification

This document records concrete, reproducible failures measured during the
integration of TwinLedger with the Genesis FinTech 2026-11-20 verification
suite, their root causes, and re-verification measurements after fixing (or
explicitly bounded limits where intentional).

---

## Failure Case 1 — Cross-Check Divergence on `D13_fx_inverse_operation_date` (Fixed & Re-Verified)

### Measured Failure (Before Fix)
When generating the 20 closed scenarios `D01..D20` (`master_seed=2026`) and
running the independent zero-common-mode verifier (`verifier/discover.py`) +
crosscheck (`scoring/crosscheck.py`):

- `D01..D12`: `12/12 PASS` (`FP=0, FN=0, F1=1.0000000`)
- **`D13_fx_inverse_operation_date` (`rate_date_rule="operation_date"`, `quote_convention="foreign_per_functional"`, `rounding_mode="half_up"`):**
  - **Measured result:** `TP=0, FP=5, FN=1, precision=0.0000000, recall=0.0000000, F1=0.0000000`, `release_blocked=True`.

### Root Cause
1. Per `spec/policy_semantics.md` and `verifier/fx_mismatch.py:52`, when
   `fx_policy.rate_date_rule == "operation_date"`, the permitted FX rate date is
   the journal entry operation timestamp (`je["timestamp"]` converted to company
   timezone), and the minimal evidence set is `{FX:<fx_id>, JE:<je_id>}`.
2. In `gen/core/clean_twin.py` and `gen/errors/operators.py`, the generator
   erroneously mapped `"operation_date"` to `inv["service_start"]` instead of
   `je["timestamp"]`, causing all 5 clean foreign-currency journal entries in
   `D13` to be converted with the `service_start` date rate rather than the
   journal operation date rate (5 false positives in verifier) and causing the
   injected truth evidence/delta to disagree with the verifier (1 false negative).

### Fix & Re-Verification (After Fix)
- Updated `gen/core/clean_twin.py` (`fx_target` for `operation_date` uses `je_ts`)
  and `gen/errors/operators.py` (`events["operation_date"] = je["timestamp"]` and
  minimal evidence set `[FX:<id>, JE:<id>]`).
- **Re-verification measurement (`tests/official/test_block2_episodes.py`):**
  - `D13_fx_inverse_operation_date`: `TP=1, FP=0, FN=0, F1=1.0000000` (`PASS`).
  - Full `D01..D20` matrix: **`20/20 PASS` (`FP=0, FN=0, F1=1.0000000`)**.

---

## Failure Case 2 — Baseline Policy Failure Modes on `D01..D20` (Measured)

All four baseline policies were evaluated across the identical 20 closed
scenarios (`master_seed=2026`, 80 total episodes, OS-isolated subprocesses for
public policies, logged in `artifacts/trajectories/trajectories.jsonl`):

| Policy | Clean (`D01..D05`) Mean Return | Single-Error (`D06..D15`) Mean Return | Interaction (`D16..D20`) Mean Return | Overall Mean F1 | Overall Mean Return |
|---|---:|---:|---:|---:|---:|
| `oracle` | `+0.9920` | `+0.9920` | `+0.9920` | `1.0000` | `+0.9920` |
| `simple_reconciliation` | `+0.9860` | `+0.9854` | `+0.9844` | `1.0000` | `+0.9853` |
| `random` | `+0.9760` | `-1.0000` | `-1.0000` | `0.2500` | `-0.5060` |
| `mass_flagging` | `-1.0000` | `-1.0000` | `-1.0000` | `0.0000` | `-1.0000` |

### Failure Analysis by Policy
1. **`random` (`mean_F1=0.2500`, `mean_return=-0.5060`):**
   - Succeeds only on the 5 clean episodes (`D01..D05`) because submitting empty
     findings satisfies the clean-book rule (`TP=FP=FN=0 -> F1=1`, return
     `1 - 0.2 * 12 / 100 = +0.9760`).
   - Fails completely on all 15 anomalous episodes (`D06..D20`, `FN >= 1 -> F1=0`,
     clipped `return=-1.0`).
2. **`mass_flagging` (`mean_F1=0.0000`, `mean_return=-1.0000`):**
   - Submits 28 structurally valid findings across the first 7 ledger entries
     (all 4 anomaly types). Even when an entry coincides with a true anomaly,
     missing required evidence sets (e.g. `INV`, `FX`, `PAY`) plus 27+ false
     positives drive `F1` near `0` and clip `return` to `-1.0`.
   - Independently corroborated by Block 3 vector #12 (`TP=1, FP=19, FN=0 ->
     F1=2/21, return=-871/1050 ≈ -0.8295`), proving reward resistance to shotgun
     flagging.

---

## Failure Case 3 — Reproducible Structural & Budget Limits (Verified Bounds)

The following reproducible failure boundaries were measured and locked via unit
tests in `tests/official/test_block1_contracts.py` and `test_block3_scorer.py`:

1. **Step-budget boundary (`C16` vs `C17`):** 99 inspection calls + `submit` on
   action 100 is accepted (`terminated=True, inspection_steps=99`); 100
   inspection calls without `submit` truncates with frozen empty findings
   (`truncated=True`, late `submit` rejected with `ALREADY_TERMINATED`).
2. **Pre-deduplication structural caps (`Block 3 #18..20`, `M05`, `M09`):**
   31 findings, 11 `evidence_ids` (even when 10 are duplicates of `D1`),
   1001-code-point `explanation`, or string/boolean `claimed_amount_minor` all
   deterministically return `{"tp": None, "fp": None, "fn": None, "precision":
   None, "recall": None, "f1": None, "return": -1.0}`.
3. **Unreachable evidence injection (`M04`):** Appending a single non-existent
   `evidence_id` `U` alongside a valid evidence set `{D1, D2}` deterministically
   prevents matching (`TP=0, FP=1, FN=1, return=-1.0`).
4. **Pagination budget ceiling for `simple_reconciliation` (unremediated design
   limit):** Because `simple_reconciliation` performs full sequential table scans
   at `limit=50`, on synthetic books whose combined rows across the 6 scanned
   tables exceed `99 * 50 = 4,950` rows, it exhausts its inspection budget before
   reading all records and submits partial findings at `remaining_steps == 1`.
