# TwinLedger Official Compliance Matrix (Genesis FinTech 2026-11-20)

Authoritative reference: `spec/official_fintech_checks_2026-11-20.md` (100 points total).

## Adapter & Access Boundary

| Requirement | Implementation | Verification |
|---|---|---|
| `generate_episode(seed, config, output_dir)` | `judge_adapter.py::generate_episode` -> `gen/pipeline.py::build_episode_from_config` | `tests/official/test_block1_contracts.py`, `test_block2_episodes.py` |
| `make_env()` with `reset(seed, config)` & `step(action)` | `judge_adapter.py::make_env` -> `adapter/official_env.py::OfficialJudgeEnv` | `tests/official/test_block1_contracts.py` (`C01..C20`) |
| `score_episode(episode_dir, findings, inspection_steps)` | `judge_adapter.py::score_episode` -> `scoring/official_scorer.py` | `tests/official/test_block3_scorer.py` (`#1..20`, `M01..M12`) |
| Process isolation for public policies | `harness/isolated_runner.py` + `arena/policies/worker.py` (OS subprocess, sanitized env, stdin/stdout JSONL) | `tests/official/test_block1_contracts.py::test_C20`, `test_block5_baselines.py`, `tools/check_import_boundaries.py` |
| Judge-side Oracle separation | `judge/oracle_policy.py` (never imported by `arena/policies/`) | `tools/check_import_boundaries.py`, `tests/official/test_block4_paired.py` |

## Block 1: 20 Contract Tests (25 pts)

| Check | Requirement Summary | Implementation | Mirror Test |
|---|---|---|---|
| C01 | `reset` returns JSON-compatible `(obs, info)` | `adapter/official_env.py::reset` | `test_block1_contracts.py::test_C01_*` |
| C02 | First obs has `task`, `manifest`, `policy`, `remaining_steps`; no seed/truth | `adapter/official_env.py::reset` | `test_C02_*` |
| C03 | `manifest` has required fields + exact record/doc counts + rounding rules | `adapter/official_env.py::load_official_public_book` | `test_C03_*` |
| C04 | `list_records` step returns `(obs, reward, terminated, truncated, info)` with bool flags | `adapter/official_env.py::step` | `test_C04_*` |
| C05 | `list_records` on fixture `L` (>=101 rows) with `limit=50` paginates cleanly over >=3 pages | `gen/pipeline.py` (`L`), `adapter/official_env.py::_handle_list_records` | `test_C05_*` |
| C06 | Re-querying same cursor returns identical rows in identical order & consumes step | `env/cursors.py::CursorCodec` | `test_C06_*` |
| C07 | `get_record` returns exact record for R1 | `adapter/official_env.py::_handle_get_record` | `test_C07_*` |
| C08 | `get_document` returns exact document for D1; no arbitrary FS access | `adapter/official_env.py::_handle_get_document` | `test_C08_*` |
| C09 | `calculator("0.1+0.2")` returns exact decimal `"0.3"` | `env/calc.py::evaluate_calc` | `test_C09_*` |
| C10 | `calculator` rejects non-arithmetic / file-access expressions safely | `env/calc.py::evaluate_calc` | `test_C10_*` |
| C11 | `get_record` for absent `U`: bounded error, step consumed | `adapter/official_env.py` | `test_C11_*` |
| C12 | `get_document` for absent `U`: bounded error, step consumed, zero disclosure | `adapter/official_env.py` | `test_C12_*` |
| C13 | Unknown action: bounded `UNKNOWN_ACTION` error, step consumed | `adapter/official_env.py` | `test_C13_*` |
| C14 | Budget decrements by 1 after both valid and error steps; data intact | `adapter/official_env.py` | `test_C14_*` |
| C15 | Valid `submit` sets `terminated=True` and freezes findings/metrics | `adapter/official_env.py` | `test_C15_*` |
| C16 | 99 inspection steps + `submit` on action 100 accepted (`inspection_steps=99`) | `adapter/official_env.py` | `test_C16_*` |
| C17 | 100 inspection steps without `submit` -> `truncated=True`, empty findings frozen | `adapter/official_env.py` | `test_C17_*` |
| C18 | Reproducible 60s timeout -> `truncated=True`, empty findings | `adapter/official_env.py` (injectable clock) | `test_C18_*` |
| C19 | Closed mode `reward == 0` on all steps including terminal; train mode returns terminal reward | `adapter/official_env.py`, `judge_adapter.py` | `test_C19_*` |
| C20 | Zero leakage across all records/docs/errors/info + OS subprocess isolation | `adapter/official_env.py`, `harness/isolated_runner.py`, `tools/check_import_boundaries.py` | `test_C20_*` |

## Block 2: 20 Closed Episodes D01..D20 (25 pts)

| Scenarios | Count | Content | Verifier F1 |
|---|---:|---|---:|
| `D01..D05` | 5 | Clean books: standard, split payment, refund/CN, recurring amounts, FX/cutoff boundary | `1.0000` (5/5) |
| `D06..D08` | 3 | `DUPLICATE_PAYMENT` with varying currencies/ID styles + recurring/refund/CN distractors | `1.0000` (3/3) |
| `D09..D11` | 3 | `PARTIAL_PAYMENT_ALLOCATION`: `missing_allocation`, `premature_paid`, `over_allocated_payment` | `1.0000` (3/3) |
| `D12..D13` | 2 | `FX_RATE_MISMATCH`: direct/document_date/half_even (KZT) vs inverse/operation_date/half_up (KWD) | `1.0000` (2/2) |
| `D14..D15` | 2 | `PERIOD_CUTOFF`: `Asia/Almaty` monthly vs `UTC` quarterly | `1.0000` (2/2) |
| `D16..D18` | 3 | Interaction #1 (`FX_PERIOD_INTERACTION`: `FX_RATE_MISMATCH` + `PERIOD_CUTOFF`) | `1.0000` (3/3) |
| `D19..D20` | 2 | Interaction #2 (`PAYMENT_ALLOCATION_INTERACTION`: `DUPLICATE_PAYMENT` + `PARTIAL_PAYMENT_ALLOCATION`) | `1.0000` (2/2) |

Verified by `tests/official/test_block2_episodes.py` using zero-common-mode `verifier/discover.py` + `scoring/crosscheck.py` + `judge_adapter.score_episode`.

## Block 3: 20 Reward Vectors & M01..M12 (25 pts)

- All 20 reward/matcher test vectors verified within `1e-9` absolute tolerance in `tests/official/test_block3_scorer.py::TestBlock3RewardVectors1To20`.
- All 12 normative matcher examples `M01..M12` verified in `tests/official/test_block3_scorer.py::TestBlock3OpenExamplesM01ToM12`.

## Block 4: 20 Paired Invariance Checks P01..P20 (15 pts)

- `P01..P05` (row permutation), `P06..P10` (bijective ID remap), `P11..P20` (both) implemented via `metamorphic/paired_transform.py` and verified end-to-end through `judge_adapter` in `tests/official/test_block4_paired.py`.
- File row order preserved verbatim; arbitrary remapped IDs accepted; FX semantic key `YYYY-MM-DD:SRC:DST` preserved; inverse-mapped findings, counts, metrics, and return match identically at equal `inspection_steps`.

## Block 5: Engineering Anchors 0/1/2 (10 pts)

| Anchor | Target | Evidence |
|---|---|---|
| Single run command | 2/2 | `make verify` / `make docker-check` (Dockerfile default `CMD ["make", "verify"]`) |
| Pinned versions & configs | 2/2 | `configs/official_eval_manifest.json`, `requirements-core.txt` (stdlib-only), Python 3.11 |
| Trajectories | 2/2 | `artifacts/trajectories/trajectories.jsonl` (80 episodes: `D01..D20` x 4 policies, zero obs leakage) |
| Measured failure analysis | 2/2 | `docs/FAILURE_ANALYSIS.md` (measured before/after verifier bug catch + measured baseline failures) |
| Honest limitations | 2/2 | `docs/LIMITATIONS.md` (every limitation linked to concrete scenarios; zero unverified RL claims) |
