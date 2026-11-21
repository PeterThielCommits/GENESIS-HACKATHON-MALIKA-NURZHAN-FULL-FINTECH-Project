# Phase 8 Report — Независимый Verifier и ProofGraph

- **Phase**: 8 (`НЕЗАВИСИМЫЙ VERIFIER И PROOFGRAPH`)
- **Date**: 2026-11-21
- **Branch**: `arena/bbc43571-genesis-hackathon-malika-nurzh` (base commit `62d7b9e00a529e2e47b3b851f74e7865e9c262ea`)
- **Master TZ**: `TwinLedger v3.0.0` (`docs/reference/TwinLedger_v3_Master_TZ_AI_Agents.txt`, SHA-256 `a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36`)
- **Outcome**: **PARTIAL** — All Phase 8 Tasks `8.1–8.7` are implemented and verified (60 new verifier/crosscheck/boundary tests PASS; 197 unit/contract tests + 3 property tests PASS; `make verify` PASS). **EXIT GATE 8** ("100% generated release episodes independently verified; else reject/rebuild") cannot yet be marked `DONE` because `episodes/dev` and `episodes/train` contain **0 generated release episodes** (upstream Phases 3–4 remain unmerged on parallel branches and issue #3 / draft CR-06-01 remain open).

## 1. Task completion matrix (Master TZ §24 Phase 8)

| Task | Description | Status | Primary artifacts |
|---|---|---|---|
| **8.1** | Freeze verifier algorithm spec without reading generator code | **DONE** | `spec/verifier_algorithm.md` (v1.0.0) |
| **8.2** | Implement independent discovery for all 4 anomaly types | **DONE** | `verifier/{public_loader,money_time,duplicate_payment,partial_allocation,fx_mismatch,period_cutoff,result,validate,discover,__main__}.py` |
| **8.3** | Implement ProofGraph DAG (5 node types, 5 edge types, deterministic DAG) | **DONE** | `verifier/proof_graph.py`, `tests/verifier/test_proof_graph.py` |
| **8.4** | Enumerate minimal/alternative evidence sets + ablation + reachability | **DONE** | `verifier/evidence.py`, `verifier/minimal_sets.py`, `tests/verifier/test_evidence_ablation.py` |
| **8.5** | Implement distractor exclusion logic (all 16 minimum distractors + counterfactual pairs) | **DONE** | `verifier/{duplicate_payment,partial_allocation,fx_mismatch,period_cutoff}.py`, `tests/verifier/test_distractors.py` |
| **8.6** | Add independent Stage-2 crosscheck against truth (`crosscheck(report, sealed_truth)`) | **DONE** | `scoring/crosscheck.py`, `tests/verifier/test_crosscheck.py` |
| **8.7** | Add import and file-access boundary tests | **DONE** | `tests/verifier/test_boundaries.py`, `docs/INDEPENDENCE.md` |

## 2. Independence & zero common-mode guarantee (TZ §12.4, §13.1)

- `gen/` was **not read** during Task 8.1 specification or Tasks 8.2–8.7 implementation.
- `verifier/` imports **only** Python 3.11 stdlib and `contracts/` (frozen schemas, canonical JSON, ISO-4217 currency exponents). It has **zero** imports from `gen/`, `core/`, `invariants/`, `scoring/`, `env/`, `harness/`, `seal/`, or `arena/`.
- `verifier/money_time.py` independently implements exact rational (`fractions.Fraction`) FX conversion (direct and inverse ISO `BASE/QUOTE` pairs, single final `half_even`/`half_up` rounding) and `zoneinfo.ZoneInfo` company-local fiscal period resolution.
- Stage-1 (`verifier.discover`) and Stage-2 (`scoring.crosscheck`) are physically separated across packages and locked by a pre-committed SHA-256 `report_digest` (REQ-ORG-003). `scoring/crosscheck.py` does not import `verifier/` or `gen/`.
- See `docs/INDEPENDENCE.md` for full shared-dependency disclosure and proof evidence.

## 3. Requirements & invariants coverage

- **Architecture & boundaries**: `REQ-ARC-001`, `REQ-ARC-007`, `REQ-ORG-001..004`, `REQ-VER-001`, `REQ-VER-002` — verified via `make lint` (`tools/check_import_boundaries.py`), AST scan, fresh-process `sys.modules` guard, runtime `io.open`/`Path.open` spy on sibling `sealed/` directory, and negative dotfile/`index_hints.json`/extra-file/symlink-escape tests.
- **ProofGraph**: `REQ-VER-003`, `REQ-VER-004`, TZ §13.4, §21.1, §21.4 — all 5 node types (`RecordNode`, `FactNode`, `RuleNode`, `CalculationNode`, `FindingNode`), all 5 edge types (`derived_from`, `supports`, `contradicts`, `governed_by`, `excludes`), strict acyclicity, every `FindingNode` traces to ≥1 `RecordNode` and ≥1 `RuleNode`, deterministic JSON serialization.
- **Ambiguities**: `REQ-VER-005` — missing/conflicting same-date FX quotes emit explicit `unresolved_ambiguities` rather than fabricated findings and cause Stage-2 `release_blocked=True`.
- **Evidence reachability & ablation**: `REQ-VER-010..014`, TZ §13.5, §21.3 — public-tool route verification (`list_records`, `get_record`, `get_document`), `policy.max_evidence_ids` enforcement, sufficiency + greedy minimization + single-element & full-set deletion ablation verified across all 4 types and multi-certificate alternatives (`evidence_enumeration_complete` cap supported).
- **Distractors & counterfactuals**: TZ §11.6, §21.2 — all 16 minimum distractors (`D-DUP-01..04`, `D-PART-01..04`, `D-FX-01..04`, `D-CUT-01..04`) produce **0 FP** with explicit ProofGraph `excludes` edges; counterfactual minimal pairs pass across all 4 anomaly types.
- **Stage-2 Crosscheck**: `REQ-VER-020..022`, TZ §13.7 — pre-committed `report_digest` validation, frozen `verifier_report.schema.json` validation, non-union per-set evidence matching via `scoring.matcher.optimal_matching`, exact `Fraction` metrics (`precision`, `recall`, `f1`, `exact_affected_id_accuracy`, `amount_exact_accuracy`, `amount_tolerance_accuracy`, `evidence_sufficiency_rate`, `evidence_minimality_rate`, `distractor_false_positive_rate`, `unresolved_ambiguity_count`), deterministic `crosscheck_hash`, and `release_blocked=True` on any defect.

## 4. Verification commands & results

| Command | Exit code | Result | Notes |
|---|---:|---|---|
| `make setup` | 0 | **PASS** | Python 3.11.2; pytest/hypothesis/jsonschema absent (optional) |
| `make lint` | 0 | **PASS** | `import boundary scan: CLEAN (REQ-ARC-001..007)` |
| `python3 -m unittest discover -s tests/verifier -t . -v` | 0 | **PASS** | 60/60 Phase 8 tests PASS |
| `make test` | 0 | **PASS** | 197/197 tests PASS (137 baseline + 60 Phase 8) |
| `make test-property` | 0 | **PASS** | 3/3 property tests PASS |
| `make verify` | 0 | **PASS** | `RC-001`, `RC-002`, `RC-003` PASS (`artifacts/reports/latest/verify_summary.json`) |
| `make report` | 0 | **PASS** | `artifacts/reports/latest/report_index.json` |
| `make docker-check` | — | **NOT RUN** | Docker unavailable in session sandbox |

## 5. Provisional assumptions & open blockers

- **Upstream episode generation blocker (EXIT GATE 8 → PARTIAL)**: `episodes/dev` and `episodes/train` currently hold 0 generated episodes because Phases 3–4 are unmerged on parallel branches and issue #3 / draft CR-06-01 remain open. Once A0 integrates Phases 3–4 + Phase 7 and generates release episodes, run `python3 -m verifier <ep>/public --out <ep>/verifier_report.json` followed by Stage-2 `scoring.crosscheck.crosscheck()` on 100% of generated episodes to promote EXIT GATE 8 to `DONE`.
- **Provisional anomaly/affected-ID semantics**: `spec/verifier_algorithm.md` follows frozen v1.0.0 contracts, `spec/anomaly_catalog.yaml`, and `docs/DATA_DICTIONARY.md`; official organiser rules remain open under `Q-004`, `Q-005`, `Q-006`.
- **Frozen contracts untouched**: zero changes to `contracts/*.schema.json` or `scoring/diagnostics.py` (default `verifier_quality: NOT_AVAILABLE` preserved for Phase 6 tests).
