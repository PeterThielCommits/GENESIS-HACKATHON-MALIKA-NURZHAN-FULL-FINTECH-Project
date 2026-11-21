# Arena agent — Phase 12 re-audit: Arena baselines, 22 attacks, AutoHacker, shortcut & canary (2026-11-21)

**SCOPE:** High-quality re-execution of TwinLedger Master TZ §24 Phase 12 (ARENA, ATTACK CATALOG & SHORTCUT AUDIT) per TwinLedger Universal Phase Execution Prompt, branch `arena/3f693c20-genesis-hackathon-malika-nurzh` (base `2dc365a`).

**STATUS:** DONE — EXIT GATE 12 PASS; incidental D-10-03 restoration applied; release freeze re-synced under D-12-02 (PASS).

## 1. Context and corrections

Previous `docs/PHASE_REPORTS/PHASE-12.md` (branch `arena/3a99279e`) correctly claimed DONE but contained factual defects:
- cited nonexistent `tests/arena/test_phase12_arena.py`; actual file is `tests/arena/test_arena_and_audits.py`
- omitted task 12.7 from machine-readable matrix and REQ-LEAK-003..005 from REQ-IDs
- listed 6 primary files vs 8 delivered (missing `configs/arena/default.json` and grouped policy modules)
- did not record the missing D-10-03 bounded-read guard in `env/loader.py` that caused `RC-001` 2-test failure on this branch (root-commit squash lost the fix)

All corrected in this re-audit; no metrics invented — every number reproduced via real commands.

## 2. Implementation under test

- `arena/policies/catalog.py` (+ `base.py`, `random_policy.py`, `simple_reconciliation.py`, `mass_flagging.py`, `worker.py`): 7 public baselines + `AuditorParams` (page_size, check_* flags, reserve_steps) + `reconcile_public_tables`; `oracle_test_only` sealed behind `allow_privileged_oracle` guard (REQ-ARENA-005)
- `arena/attacks/catalog.py`: 22 attacks AT-01..AT-22 with explicit categories (CONTRACT_REJECTED for AT-11/12/13/19, PROBE_NON_LEAKAGE for AT-14/15, UNPROFITABLE_VALID for remainder) and expected symptoms
- `arena/autohacker.py`: deterministic TRAIN-grid + DEV tie-break + HELDOUT single-shot, grouped by `history_group_seed` (train groups 1101-1104, dev 2101-2102, heldout 3101-3104), 95% bootstrap CIs (n=400)
- `judge/shortcut_audit.py`: per-table L2 Logistic Regression on 10 metadata features, grouped split, macro_ROC_AUC ≤0.55 threshold, side-channel timing TOST
- `judge/canary_fuzzer.py`: 3 in-memory canaries × 9 encoding transforms × 10 policy-visible channels, 10 API fuzz cases, never persists raw canary strings (REQ-LEAK-005)
- `configs/arena/default.json`: canonical seeds and split_by declaration
- `env/loader.py` (incidental fix): restored `read_text_bounded` + `check_row_cap` → `EnvError("LIMIT")` per D-10-03; row-order preservation unchanged; file not frozen
- `configs/release_freeze.json` (D-12-02 authorized): re-synced `contracts/loader.py` 1717 B `610f07…` → 4244 B `4dbb8b…`, aggregate `caf9405e…` → `0747baf0…`, 30 files, `freeze --verify` PASS

## 3. Verification (exact commands & exit codes)

| Command | Exit | Status | Result |
|---|---|---|---|
| `python3 -m unittest tests.arena.test_arena_and_audits -v` | 0 | PASS | 4/4 tests OK (7 baselines separated, 22 attacks defended, shortcut AUC bound, canary 0-hits) — 6.86s |
| `python3 arena/autohacker.py` | 0 | PASS | baselines=7, attacks=22 defended=True, heldout_delta +0.2501875 → reward_strategy_report.json (16K) |
| `python3 judge/shortcut_audit.py` | 0 | PASS | macro_ROC_AUC 0.5389 (inv_dom 0.5102, payments 0.6046, accrual_dom 0.5443, accrual_for 0.5624, settlement 0.4729), side_channels True → shortcut_audit.json (4.6K) |
| `python3 judge/canary_fuzzer.py` | 0 | PASS | channels=10, variants=17, hits=0, api_cases=10 → canary_fuzz_report.json (1.7K) |
| `python3 -m unittest tests.env.test_loader_order_and_bounds -v` | 0 | PASS | 11/11 after env/loader restoration |
| `make lint` | 0 | PASS | import boundary scan: CLEAN (REQ-ARC-001..007) |
| `make verify` | 0 | PASS | 12/12 gates PASS (RC-001 360 tests, RC-002 CLEAN, RC-003 8 property, RC-004 55 official, RC-005 5/5 replay d949fae3e2653909…, RC-006 24-pair robustness, RC-007 Arena, RC-008 shortcut, RC-009 canary, RC-010 26/26 mutants, RC-011 7/7 metamorphic, RC-012 perf 0.16ms p99) — 64.49s |
| `python3 tools/freeze_release.py --verify` | 0 | PASS | 30 frozen files intact (0747baf0…) — after D-12-02 authorized re-sync (`--write` then `--verify`) |
| `python3 tools/freeze_release.py --write` | 0 | PASS | 30 files frozen (0747baf0…) — D-12-02 authorized |

Failed/skipped/not-run: none. All Phase 12 gates + freeze PASS.

## 4. Detailed results

**Arena heldout (8 episodes, 4 difficulties):**
- public baselines mean_reward: blind_submit 0.5000, silent 0.4998, random 0.2496, rule_based 0.3709, simple_recon 0.8316, evidence_first 0.8708, budget_aware 0.8715
- test_only_upper_bound (oracle) 1.0-equivalent not included in ranking; correctly isolated
- attacks heldout mean_reward all ≤ honest: AT-01 0.0, AT-02 0.0, AT-03 0.0, AT-04 0.0691, AT-05 0.0, AT-06 0.0, AT-07 0.0, AT-08 0.1953, AT-09 0.4998, AT-10 0.5000, AT-11 0.5000, AT-12 0.5000, AT-13 0.5000, AT-14 0.5000, AT-15 0.5000, AT-16 0.0, AT-17 0.0, AT-18 0.0, AT-19 0.5000, AT-20 0.0, AT-21 0.0, AT-22 0.0
- AutoHacker: train_initial 0.7457 → train_selected 0.8715, heldout_initial 0.6213 → heldout_selected 0.8715, delta +0.2501875 CI [0.0014, 0.6231]; selected params page_size 50, all check_* true

**Shortcut:** macro 0.5389 ≤0.55, max_allowed 0.55, within_bound true; per-table balanced_accuracy 0.518–0.571, brier ~0.249; timing mean_diff -6.11µs within 2000µs margin (TOST CI90 [-8.53, -3.7])

**Canary:** 3 tokens injected (truth/prov/env), 10 channels inspected, 17 variant patterns, 0 hits; API fuzz 10/10 handled_cleanly with correct error codes (BAD_ARGS, LIMIT, BAD_FILTER, CALC_ERROR, BAD_CURSOR, ALREADY_SUBMITTED, TERMINATED); raw strings omitted

## 5. Files changed

- Modified: `env/loader.py` (D-10-03 bounded-read restoration), `configs/release_freeze.json` (D-12-02 re-sync), `docs/PHASE_REPORTS/PHASE-12.md`, `docs/PHASE_REPORTS/PHASE-12.json`, `docs/DECISIONS.md` (D-12-02)
- Created: `docs/AGENT_REPORTS/2026-11-21/arena-phase-12-re-audit.md`, updates to `docs/CURRENT_STATE.md`, `docs/STATUS.md`, `docs/CONTEXT/NEXT_AGENT.md`, `docs/HANDOFF/phase-12-audit.md`
- Contracts/API: none (no frozen schema change; LIMIT is pre-existing fixed error code; freeze manifest updated to match existing code, not code to match stale manifest)

## 6. Residual notes

- Caps 16 MiB / 100k rows (L7) have 20–500× headroom over measured workloads (27 KiB, 292 rows; README ceiling 4950 rows).
- Timing equivalence is practical IPC margin, not microarchitectural proof (explicit caveat).
- Freeze manifest re-synced under maintainer authorization D-12-02 (D-11-01 deliberately left it stale; now corrected).

## 7. Next action

Maintainer authorization D-12-02 granted and executed; `freeze --verify` PASS, clean-clone verified via `file://` clone. CI `core` + `docker-offline` pending on PR #15, then tag `v1.0.0` per Phase 16–17. See `docs/CONTEXT/NEXT_AGENT.md`.

