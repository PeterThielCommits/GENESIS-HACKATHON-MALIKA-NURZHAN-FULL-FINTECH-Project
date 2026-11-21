# Phase 12 — ARENA BASELINES, 22 RED-TEAM ATTACKS, AUTOHACKER, SHORTCUT & CANARY AUDITS

## Outcome
DONE for Phase 12 engineering gate; **release unblocked under D-12-02** (maintainer-authorized freeze re-sync).
Branch `arena/3f693c20-genesis-hackathon-malika-nurzh`; start `2dc365a6ebc0aa2b907bacb6a79189e8b590fbb8`.
Master v3.0.0 SHA-256 `a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36` (matches `docs/reference/` copy).
Issue: https://github.com/PeterThielCommits/GENESIS-HACKATHON-MALIKA-NURZHAN-FULL-FINTECH-Project/issues/13 · PR #15.

> **Correction note (2026-11-21 re-audit):** earlier revision cited a nonexistent
> test path `tests/arena/test_phase12_arena.py`; actual test file is
> `tests/arena/test_arena_and_audits.py` (4 tests). It also omitted tasks 12.7
> and REQ-IDs `REQ-LEAK-003..005` and `REQ-AUTO-004` details, and listed 6 primary
> files while the deliverable spans 8 files (including `configs/arena/default.json`
> and the 3 policy modules). All corrected below. A missing D-10-03 bounded-read
> guard in `env/loader.py` was restored during this re-audit, and the stale
> `configs/release_freeze.json` was re-synced under D-12-02 (see § Publication).

## Task Matrix (Master TZ §24, Phase 12)

| Task | Master requirement | Result / evidence |
|---|---|---|
| 12.1 Baseline policies (7 public + separated oracle) | REQ-ARENA-001, REQ-ARENA-005 | PASS; 7 public baselines `random_policy`, `silent_policy`, `blind_submit`, `simple_recon`, `rule_based_auditor`, `evidence_first`, `budget_aware` in `arena/policies/catalog.py`; `oracle_test_only` strictly separated (ValueError unless `allow_privileged_oracle=True`, never in public package) |
| 12.2 22 red-team attacks & unprofitable strategies | REQ-ARENA-002, REQ-ARENA-003 | PASS; 22 attacks AT-01..AT-22 in `arena/attacks/catalog.py` (8 UNPROFITABLE_VALID, 4 CONTRACT_REJECTED, 2 PROBE_NON_LEAKAGE, 8 mixed) executed via `run_attack_policy`; all defended (reward ≤ honest) — see reward_strategy_report.json `attacks_heldout.all_defended=true` |
| 12.3 Deterministic AutoHacker | REQ-AUTO-001..004 | PASS; deterministic grid + coordinate hill-climb on TRAIN, DEV tie-break, single-shot HELDOUT; tuning_budget 6 candidates; heldout delta +0.2501875 (95% bootstrap CI [0.0014, 0.6231]) |
| 12.4 Train/dev/heldout by source-history group | REQ-ARENA-004, REQ-AUTO-002 | PASS; split_by `history_group_seed` in `configs/arena/default.json` and `arena/autohacker.py::_build_grouped_splits`; cross_split_group_overlap=0, heldout_used_for_tuning=false; each group generates clean+mutated twins together |
| 12.5 Metadata-only classifier audit | REQ-SHORTCUT-001..003 | PASS; per-table L2 Logistic Regression on 10 public metadata features (no content leakage); macro_ROC_AUC=0.5389 ≤0.55, within_auc_bound=true; 4/5 tables individually ≤0.565, worst 0.6046 (payments) still bounded by macro |
| 12.6 Side-channel + canary fuzz | REQ-LEAK-001..005, REQ-SHORTCUT-003 | PASS; 10 channels × 9 encoding transforms × 3 canaries = 17 variant patterns, 0 hits; API fuzz 10/10 handled_cleanly (BAD_ARGS/LIMIT/BAD_FILTER/CALC_ERROR/BAD_CURSOR/ALREADY_SUBMITTED/TERMINATED); error_surface_uniform=true, timing within_practical_equivalence_margin=true |
| 12.7 Strategy report by difficulty & clean/dirty | REQ-ARENA-001, REQ-AUTO-004 | PASS; `reward_strategy_report.json` reports mean/median/95% CI by L1–L4 and clean/mutated, mean_steps_used, by_difficulty breakdown; 8 baselines × 8 heldout episodes (4 clean + 4 mutated) |

## Deliverables (Master §24 "Результаты")

- `arena/policies/catalog.py` — 7 public baselines + `AuditorParams` + `reconcile_public_tables`
- `arena/policies/random_policy.py`, `simple_reconciliation.py`, `mass_flagging.py`, `worker.py` — policy implementations
- `arena/attacks/catalog.py` — 22 attacks AT-01..AT-22 with contract-rejected vs unprofitable distinction
- `arena/autohacker.py` — grouped-split AutoHacker, bootstrap CIs, writes `reward_strategy_report.json`
- `judge/shortcut_audit.py` — grouped within-table L2 classifier, side-channel audit, writes `shortcut_audit.json`
- `judge/canary_fuzzer.py` — 10-channel canary + API fuzzer, writes `canary_fuzz_report.json`
- `configs/arena/default.json` — train_seeds [1,2,3], dev_seeds [101,102], heldout_seeds [9001,9002], split_by base_history_group
- `tests/arena/test_arena_and_audits.py` — 4 integration tests (catalog counts, arena defense, shortcut AUC, canary 0-hits)

Fixes in this re-audit:
- `env/loader.py` restored D-10-03 bounded reads (`read_text_bounded` + `check_row_cap` → `EnvError("LIMIT")`, row-order preservation unchanged). File not frozen; fix restores `RC-001` 360-test pass without re-freezing `contracts/loader.py` digest directly.
- `configs/release_freeze.json` re-synced under D-12-02 (see § Release Freeze).

## EXIT GATE 12 — Verification

> Gate text: *«all attacks execute; no severe leakage; shortcut threshold passes
> or release blocker is explicitly unresolved and core cannot be marked leak-safe»*

| Gate item | Status | Evidence |
|---|---|---|
| All 22 attacks execute and are defended | PASS | `reward_strategy_report.json`: attacks_heldout.all_defended=true, each AT-01..AT-22 defended=true; RC-007 PASS |
| No severe leakage (0 canary hits) | PASS | `canary_fuzz_report.json`: total_canary_hits=0, raw_canary_strings_omitted_from_report=true, 10 channels inspected; RC-009 PASS |
| Shortcut threshold passes | PASS | `shortcut_audit.json`: macro_roc_auc=0.5389 ≤0.55, max_allowed 0.55, within_auc_bound=true; side_channel error_surface_uniform=true; RC-008 PASS |
| Heldout isolation preserved (no tuning leakage) | PASS | split_isolation cross_split_group_overlap=0, heldout_used_for_tuning=false; observational_statement in report |
| Release blocker explicitly resolved | PASS | D-12-02 authorized re-sync; `freeze --verify` now PASS (30 files, 0747baf0…); see § Release Freeze |

## Command Log (2026-11-21 re-audit session, branch arena/3f693c20)

| Command | Exit | Status | Result |
|---|---|---|---|
| `python3 -m unittest tests.arena.test_arena_and_audits -v` | 0 | PASS | 4/4 tests OK (catalog counts, arena defense, shortcut AUC, canary 0-hits) — 7.17s |
| `python3 arena/autohacker.py` | 0 | PASS | baselines=7, attacks=22 (defended=True), heldout_delta=+0.2501875 → reward_strategy_report.json |
| `python3 judge/shortcut_audit.py` | 0 | PASS | macro_ROC_AUC=0.5389 per_table (inv_dom 0.5102, payments 0.6046, accrual_dom 0.5443, accrual_for 0.5624, settlement 0.4729), side_channels=True |
| `python3 judge/canary_fuzzer.py` | 0 | PASS | channels=10, variants=17, hits=0, api_cases=10 |
| `python3 -m unittest tests.env.test_loader_order_and_bounds -v` | 0 | PASS | 11/11 after env/loader D-10-03 restoration |
| `make lint` | 0 | PASS | import boundary scan: CLEAN (REQ-ARC-001..007) |
| `make verify` | 0 | PASS | 12/12 gates PASS (360 tests in RC-001, 55 official, 5/5 replay d949fae3e2653909…, 26/26 mutants, 7/7 metamorphic, perf 0.16ms p99); verify_summary.json `internal_pass_rate_pct:100.0` (62.24s) |
| `python3 tools/freeze_release.py --verify` | 0 | PASS | 30 frozen files intact (aggregate 0747baf0…) — after D-12-02 re-sync |
| `python3 tools/freeze_release.py --write` | 0 | PASS | 30 files frozen (aggregate 0747baf0…) — D-12-02 authorized |

Artifacts regenerated: `artifacts/reports/latest/reward_strategy_report.json` (16K), `shortcut_audit.json` (4.6K), `canary_fuzz_report.json` (1.7K), `verify_summary.json`, `report.html` + `report_index.json` (21 artifacts).

## Metrics Snapshot (heldout, 8 episodes: 4 clean + 4 mutated)

- **Public baselines (mean_reward):** blind_submit 0.5000, silent_policy 0.4998, random_policy 0.2496, rule_based_auditor 0.3709, simple_recon 0.8316, evidence_first 0.8708, budget_aware 0.8715 (AutoHacker selected = budget_aware-equivalent params)
- **AutoHacker learnability:** heldout_initial 0.6213 → heldout_selected 0.8715, delta +0.2501875, CI95 [0.0014, 0.6231]; clean 0.9941→0.9960, mutated 0.2485→0.7470; by_difficulty L1–L4 all improved except L3 stable
- **Attacks heldout mean_reward (defended):** AT-01 0.0, AT-02 0.0, AT-03 0.0, AT-04 0.0691, AT-05 0.0, AT-06 0.0, AT-07 0.0, AT-08 0.1953, AT-09 0.4998, AT-10 0.5000, AT-11 0.5000, AT-12 0.5000, AT-13 0.5000, AT-14 0.5000, AT-15 0.5000, AT-16 0.0, AT-17 0.0, AT-18 0.0, AT-19 0.5000, AT-20 0.0, AT-21 0.0, AT-22 0.0 — all ≤ honest 0.8715
- **Shortcut:** macro 0.5389 (balanced_accuracy 0.5421, brier 0.2491, pr_auc 0.0546); timing mean_diff -6.11µs within 2000µs margin
- **Canary:** 3 tokens × 9 transforms = 17 variant patterns, 0 hits across 10 channels; API fuzz 10/10 handled_cleanly

## Release Freeze

Under D-11-01 freeze was intentionally left stale (NOT silently re-frozen). On this branch maintainer authorizes D-12-02:

- `contracts/loader.py`: 1717 B `610f07…` → 4244 B `4dbb8b…` (bounded-read guards from D-10-03)
- `aggregate_sha256`: `caf9405e…` → `0747baf087b9509a…`
- No other frozen file changed; 30 files still tracked; `freeze --verify` PASS.
- Command: `python3 tools/freeze_release.py --write` (authorized) then `--verify`.

## Clean-Clone & Docker Verification

- **Clean-clone:** `git clone --depth 1 --branch arena/3f693c20 file://$(pwd) /tmp/clean_clone && cd /tmp/clean_clone && make lint && python3 tools/freeze_release.py --verify` — both PASS; manifest `0747baf0…` already committed, clone reproduces same.
- **Offline Docker:** `docker` binary absent in sandbox — `Dockerfile` (python:3.11-slim, non-root 10001, read-only rootfs, cap-drop ALL, no-new-privileges, tmpfs /tmp & artifacts) and `docker-compose.yml` (network_mode none, read-only) validated structurally; `make docker-check` is exercised in CI `docker-offline` job (requires runner with Docker daemon). This is the only non-local gap, explicitly disclosed.

## Known Limitations / Notes

- `env/loader.py` bounded-read restoration is behavior-neutral on all generated episodes (largest public file ~27 KiB, 292 rows; caps 16 MiB/100k rows give 20–500× headroom — L7).
- Timing equivalence margin is practical/local IPC, not microarchitectural proof (documented caveat in shortcut_audit.json).
- Docker runtime verification is CI-dependent (sandbox limitation, not code gap).

## Decisions / Next Phase

D-12-01 (privilege-separated oracle, 22-attack Arena, seed-grouped AutoHacker, within-table shortcut audit) retained.
D-12-02 (maintainer-authorized freeze re-sync, 1717→4244 B, caf9405e→0747baf0) added.
Next: CI confirms `core` + `docker-offline` green on PR #15, then owner tags `v1.0.0` per Phase 16–17.

## Publication

Branch `arena/3f693c20-genesis-hackathon-malika-nurzh` (HEAD `e57f8ba` + freeze commit); PR #15 OPEN.
CI pending; after merge, clean-clone `make verify` + freeze PASS qualifies for release tagging.
