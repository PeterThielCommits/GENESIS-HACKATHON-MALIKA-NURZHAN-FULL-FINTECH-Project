# RUBRIC TRACEABILITY

Organizer criterion → REQ id → internal check → command → artifact.

**This file is generated** by `python3 -m tools.gen_traceability --write` from
`judge/rubric_map.json` and `docs/REQUIREMENTS.json`; `make lint` and `GOV-RUBRIC-01` fail if it
is stale. Do not edit it by hand — edit the registries.

## Status of the official rubric

**There is no official rubric in this repository.** `configs/rubric/provisional.json` records `official_rubric_available: false` and `judge/rubric_map.json` marks every entry `official: false`. The block weights below are our *preliminary* reading of the master specification §0.3 and must be replaced — never silently reinterpreted — when the organizers publish the real rubric (Q-012).

| Block | Provisional points | Assumed official checks | Internal checks (implemented / planned) |
|-------|-------------------|------------------------|------------------------------------------|
| `contract_isolation` — Contract and isolation | 25 | 20 | 11 (6 / 5) |
| `data_truth` — Data and reference | 25 | 20 | 10 (0 / 10) |
| `reward_robustness` — Reward robustness | 25 | 20 | 8 (0 / 8) |
| `reproducibility` — Reproducibility | 15 | 20 | 5 (0 / 5) |
| `engineering` — Engineering | 10 | 5 | 11 (11 / 0) |
| **Total** | **100** | **85** | **45** (17 implemented) |

## Requirement coverage

`122 / 186` requirements from `docs/REQUIREMENTS.json` are mapped to at least one internal check today. `64` are not, and every one of them belongs to a phase that does not exist yet. They are **not** silently dropped: the list below is generated from the registry, so the gap stays visible and countable.

| Area | Unmapped requirements |
|------|-----------------------|
| `ADAPTER` | 1: REQ-ADAPTER-004 |
| `ARC` | 4: REQ-ARC-004, REQ-ARC-005, REQ-ARC-006, REQ-ARC-007 |
| `ARENA` | 3: REQ-ARENA-003, REQ-ARENA-004, REQ-ARENA-005 |
| `CONTRACT` | 3: REQ-CONTRACT-003, REQ-CONTRACT-020, REQ-CONTRACT-022 |
| `DATA` | 4: REQ-DATA-001, REQ-DATA-003, REQ-DATA-004, REQ-DATA-005 |
| `GEN` | 9: REQ-GEN-006, REQ-GEN-010, REQ-GEN-011, REQ-GEN-012, REQ-GEN-020, REQ-GEN-021, REQ-GEN-022, REQ-GEN-030, REQ-GEN-031 |
| `GH` | 3: REQ-GH-002, REQ-GH-004, REQ-GH-008 |
| `JUDGE` | 1: REQ-JUDGE-004 |
| `LEAK` | 3: REQ-LEAK-003, REQ-LEAK-004, REQ-LEAK-005 |
| `NLP` | 5: REQ-NLP-001, REQ-NLP-002, REQ-NLP-003, REQ-NLP-004, REQ-NLP-005 |
| `OPS` | 1: REQ-OPS-004 |
| `ORG` | 10: REQ-ORG-001, REQ-ORG-002, REQ-ORG-003, REQ-ORG-004, REQ-ORG-005, REQ-ORG-011, REQ-ORG-012, REQ-ORG-013, REQ-ORG-015, REQ-ORG-016 |
| `PROD` | 10: REQ-PROD-002, REQ-PROD-004, REQ-PROD-008, REQ-PROD-010, REQ-PROD-012, REQ-PROD-020, REQ-PROD-021, REQ-PROD-022, REQ-PROD-023, REQ-PROD-024 |
| `SEAL` | 1: REQ-SEAL-013 |
| `TEST` | 2: REQ-TEST-001, REQ-TEST-003 |
| `UNIQUE` | 4: REQ-UNIQUE-001, REQ-UNIQUE-002, REQ-UNIQUE-003, REQ-UNIQUE-004 |

## Check matrix

| Check | Block | Phase | State | Requirements | Command | Artifact |
|-------|-------|-------|-------|--------------|---------|----------|
| `CT-CONTRACTS-01` | `contract_isolation` | PHASE-00 | IMPLEMENTED | REQ-CONTRACT-002, REQ-CONTRACT-004 | `python -m tools.validate_contracts` | `artifacts/reports/latest/contracts_report.json` |
| `CT-CONTRACTS-02` | `contract_isolation` | PHASE-00 | IMPLEMENTED | REQ-CONTRACT-001, REQ-CONTRACT-004 | `python -m unittest tests.contracts.test_schema_self_consistency` | `artifacts/reports/latest/verify_summary.json` |
| `CT-CANON-01` | `contract_isolation` | PHASE-00 | IMPLEMENTED | REQ-CONTRACT-010, REQ-CONTRACT-011, REQ-CONTRACT-012 | `python -m unittest tests.unit.test_canonical_json` | `artifacts/reports/latest/verify_summary.json` |
| `CT-ADAPTER-01` | `contract_isolation` | PHASE-00 | IMPLEMENTED | REQ-ADAPTER-001, REQ-ADAPTER-002, REQ-ADAPTER-003 | `python -m unittest tests.unit.test_adapter_compatibility` | `artifacts/reports/latest/verify_summary.json` |
| `CT-BOUNDARY-01` | `contract_isolation` | PHASE-00 | IMPLEMENTED | REQ-ARC-001, REQ-ARC-002, REQ-ARC-003 | `python -m tools.check_import_boundaries` | `artifacts/reports/latest/import_boundaries_report.json` |
| `CT-ENV-01` | `contract_isolation` | PHASE-05 | PLANNED | REQ-ENV-001, REQ-ENV-002, REQ-ENV-003, REQ-ENV-004 | `make test` | `artifacts/reports/latest/verify_summary.json` |
| `CT-ENV-02` | `contract_isolation` | PHASE-05 | PLANNED | REQ-ENV-010, REQ-ENV-011, REQ-ENV-012, REQ-ENV-013 | `make test` | `artifacts/reports/latest/verify_summary.json` |
| `CT-ENV-03` | `contract_isolation` | PHASE-05 | PLANNED | REQ-ENV-020, REQ-ENV-021, REQ-ENV-022, REQ-ENV-023 | `make test` | `artifacts/reports/latest/verify_summary.json` |
| `CT-SEAL-01` | `contract_isolation` | PHASE-08 | PLANNED | REQ-ENV-030, REQ-ENV-031, REQ-ENV-032, REQ-SEAL-004 | `make verify` | `artifacts/reports/latest/verify_summary.json` |
| `CT-SEAL-02` | `contract_isolation` | PHASE-08 | PLANNED | REQ-SEAL-001, REQ-SEAL-002, REQ-SEAL-003, REQ-SEAL-005 | `make verify` | `artifacts/reports/latest/security_report.json` |
| `CT-GOLDEN-01` | `contract_isolation` | PHASE-01 | IMPLEMENTED | REQ-CONTRACT-021, REQ-GH-005 | `python3 -m tools.check_golden` | `artifacts/reports/latest/golden_report.json` |
| `DT-MONEY-01` | `data_truth` | PHASE-02 | PLANNED | REQ-MONEY-001, REQ-MONEY-002, REQ-MONEY-003, REQ-MONEY-004, REQ-MONEY-005, REQ-MONEY-006 | `make test` | `artifacts/reports/latest/verify_summary.json` |
| `DT-TIME-01` | `data_truth` | PHASE-02 | PLANNED | REQ-TIME-001, REQ-TIME-002, REQ-TIME-003, REQ-TIME-004, REQ-TIME-005 | `make test` | `artifacts/reports/latest/verify_summary.json` |
| `DT-GEN-01` | `data_truth` | PHASE-03 | PLANNED | REQ-PROD-001, REQ-GEN-001, REQ-GEN-002, REQ-GEN-005 | `make build-episodes && make replay` | `artifacts/reports/latest/replay_report.json` |
| `DT-GEN-02` | `data_truth` | PHASE-03 | PLANNED | REQ-GEN-003, REQ-GEN-004, REQ-ERR-002 | `make test-property` | `artifacts/reports/latest/metamorphic_report.json` |
| `DT-ERR-01` | `data_truth` | PHASE-04 | PLANNED | REQ-ERR-001, REQ-ERR-003, REQ-ERR-004, REQ-ERR-005, REQ-ERR-020, REQ-ERR-021, REQ-ERR-022 | `make test` | `artifacts/reports/latest/episode_matrix.csv` |
| `DT-TRUTH-01` | `data_truth` | PHASE-04 | PLANNED | REQ-INV-001, REQ-INV-002, REQ-INV-003 | `make verify` | `artifacts/reports/latest/invariants_report.json` |
| `DT-TRUTH-02` | `data_truth` | PHASE-02 | PLANNED | REQ-INV-004, REQ-INV-005 | `make test` | `artifacts/reports/latest/invariants_report.json` |
| `DT-VER-01` | `data_truth` | PHASE-06 | PLANNED | REQ-VER-001, REQ-VER-002, REQ-VER-020, REQ-VER-021, REQ-VER-022 | `make verify` | `artifacts/reports/latest/verifier_report_index.json` |
| `DT-VER-02` | `data_truth` | PHASE-06 | PLANNED | REQ-VER-003, REQ-VER-004, REQ-VER-005, REQ-VER-010, REQ-VER-011, REQ-VER-012, REQ-VER-013, REQ-VER-014 | `make verify` | `artifacts/reports/latest/verifier_report_index.json` |
| `DT-LEAK-01` | `data_truth` | PHASE-12 | PLANNED | REQ-DATA-002, REQ-DATA-020, REQ-LEAK-001, REQ-LEAK-002 | `make audit-shortcuts` | `artifacts/reports/latest/shortcut_audit.json` |
| `RW-MATCH-01` | `reward_robustness` | PHASE-09 | PLANNED | REQ-SCORE-001, REQ-SCORE-002, REQ-SCORE-003, REQ-SCORE-004, REQ-SCORE-005 | `make test` | `artifacts/reports/latest/verify_summary.json` |
| `RW-MATCH-02` | `reward_robustness` | PHASE-09 | PLANNED | REQ-SCORE-002, REQ-SCORE-004 | `make test` | `artifacts/reports/latest/reward_strategy_report.json` |
| `RW-SANITY-01` | `reward_robustness` | PHASE-09 | PLANNED | REQ-SCORE-001, REQ-PROD-011 | `python -m unittest tests.scoring.test_sanity_examples` | `artifacts/reports/latest/reward_strategy_report.json` |
| `RW-PROP-01` | `reward_robustness` | PHASE-09 | PLANNED | REQ-SCORE-003, REQ-SCORE-004, REQ-PROD-007 | `make test` | `artifacts/reports/latest/reward_strategy_report.json` |
| `RW-MUT-01` | `reward_robustness` | PHASE-13 | PLANNED | REQ-PROD-025, REQ-TEST-002 | `make mutation-test` | `artifacts/reports/latest/mutation_test_report.json` |
| `RW-ATTACK-01` | `reward_robustness` | PHASE-12 | PLANNED | REQ-PROD-005, REQ-PROD-006, REQ-PROD-007, REQ-ARENA-001, REQ-ARENA-002 | `make test` | `artifacts/reports/latest/reward_strategy_report.json` |
| `RW-DIAG-01` | `reward_robustness` | PHASE-09 | PLANNED | REQ-SCORE-001, REQ-PROD-011 | `make test` | `artifacts/reports/latest/reward_strategy_report.json` |
| `RW-TOL-01` | `reward_robustness` | PHASE-09 | PLANNED | REQ-MONEY-005, REQ-PROD-003 | `make verify` | `artifacts/reports/latest/reward_strategy_report.json` |
| `RP-DET-01` | `reproducibility` | PHASE-03 | PLANNED | REQ-PROD-001, REQ-DATA-021 | `make build-episodes && make replay` | `artifacts/reports/latest/replay_report.json` |
| `RP-REPLAY-01` | `reproducibility` | PHASE-08 | PLANNED | REQ-SEAL-030, REQ-SEAL-031, REQ-SEAL-021 | `make replay` | `artifacts/reports/latest/replay_report.json` |
| `RP-SEAL-01` | `reproducibility` | PHASE-08 | PLANNED | REQ-SEAL-010, REQ-SEAL-011, REQ-SEAL-012, REQ-SEAL-020, REQ-SEAL-022, REQ-SEAL-023 | `make verify` | `artifacts/reports/latest/seal_report.json` |
| `RP-META-01` | `reproducibility` | PHASE-13 | PLANNED | REQ-PROD-001, REQ-PROD-009 | `make test-property` | `artifacts/reports/latest/metamorphic_report.json` |
| `RP-ENVISO-01` | `reproducibility` | PHASE-08 | PLANNED | REQ-PROD-009, REQ-TEST-004 | `make test` | `artifacts/reports/latest/verify_summary.json` |
| `EN-VERIFY-01` | `engineering` | PHASE-00 | IMPLEMENTED | REQ-JUDGE-001, REQ-JUDGE-002, REQ-JUDGE-003 | `make verify` | `artifacts/reports/latest/verify_summary.json` |
| `EN-GOV-01` | `engineering` | PHASE-00 | IMPLEMENTED | REQ-ORG-010, REQ-ORG-014, REQ-GH-006, REQ-CONTRACT-005 | `python -m tools.check_governance` | `artifacts/reports/latest/governance_report.json` |
| `EN-DOCS-01` | `engineering` | PHASE-00 | IMPLEMENTED | REQ-CONTRACT-005, REQ-GH-006, REQ-JUDGE-005 | `python -m tools.check_governance` | `artifacts/reports/latest/governance_report.json` |
| `EN-ARCHIVE-01` | `engineering` | PHASE-00 | IMPLEMENTED | REQ-ADAPTER-001, REQ-GH-007 | `python -m tools.check_governance` | `artifacts/reports/latest/governance_report.json` |
| `EN-OFFLINE-01` | `engineering` | PHASE-00 | IMPLEMENTED | REQ-OPS-001, REQ-OPS-002 | `python -m tools.check_import_boundaries` | `artifacts/reports/latest/dependency_report.json` |
| `EN-DATA-01` | `engineering` | PHASE-00 | IMPLEMENTED | REQ-DATA-022, REQ-GH-007 | `python -m unittest tests.phase0.test_git_data_policy` | `artifacts/reports/latest/verify_summary.json` |
| `EN-REPORT-01` | `engineering` | PHASE-00 | IMPLEMENTED | REQ-GH-003, REQ-JUDGE-002 | `python -m unittest tests.phase0.test_phase_report` | `artifacts/reports/latest/verify_summary.json` |
| `EN-MODELS-01` | `engineering` | PHASE-01 | IMPLEMENTED | REQ-ARC-001, REQ-CONTRACT-021 | `python3 -m tools.check_models` | `artifacts/reports/latest/models_report.json` |
| `EN-CI-01` | `engineering` | PHASE-01 | IMPLEMENTED | REQ-ARC-001, REQ-TEST-004 | `python3 -m tools.check_ci` | `artifacts/reports/latest/ci_report.json` |
| `EN-SUBMIT-01` | `engineering` | PHASE-00 | IMPLEMENTED | REQ-GH-001, REQ-OPS-003 | `python3 -m unittest tests.phase0.test_deadline` | `artifacts/reports/latest/verify_summary.json` |
| `EN-PROBE-01` | `engineering` | PHASE-00 | IMPLEMENTED | REQ-ADAPTER-001, REQ-TEST-004 | `python3 -m tools.probe_starter` | `artifacts/reports/latest/starter_probe_report.json` |

## Rules

* **internal_checks_are_not_official** — Every entry has official=false and must never change until an archived official rubric exists.
* **no_official_score_claim** — Reports may show an internal pass rate only; section 23.6 forbids presenting it as the jury score.
* **one_check_one_command** — Each check names a reproducible command and the artifact it produces.
* **req_traceability** — Every check cites REQ ids that exist in docs/REQUIREMENTS.json.

## How a check appears in `make verify`

* `IMPLEMENTED` checks are executed; their status is `PASS`, `FAIL` or `SKIPPED` with a real command and an artifact reference.
* `PLANNED` checks are emitted as `BLOCKED` with the phase that will implement them. They are never counted as passing and never omitted from the report.
* A check whose dependency is absent is `SKIPPED` with a reason (REQ-JUDGE-003).
* Exit code `0` requires every executed check to pass; `4` is reserved for a release blocker (leak or a false official claim).

## When the official rubric arrives

1. Archive it under `docs/official/` with `classification: OFFICIAL_ORGANIZER` and its SHA-256.
2. Open a `docs/CR/` entry describing the diff against these provisional blocks.
3. Add a mirrored internal test per official check and set `official: true` with the quoted source and identifier.
4. Set `official_rubric_available: true` — only then may a report carry an official figure.
5. Re-run `make verify` and regenerate this file; the phase report records the new numbers.
