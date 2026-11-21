# Phase 10 Report — MULTILINGUAL TEXT LAYER (RU/KK/EN), NLP NORMALIZATION & EVIDENCE HIERARCHY

- **Status:** `DONE` (`EXIT GATE 10: DONE`)
- **Master TZ:** `TwinLedger_v3_Master_TZ_AI_Agents.txt` v3.0.0, sha256 `a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36` (matches `docs/reference/` copy)
- **Requirements Covered:** `REQ-NLP-001`, `REQ-NLP-002`, `REQ-NLP-003`, `REQ-NLP-004`, `REQ-NLP-005`, `REQ-PROD-020`, `REQ-ARC-001`, `REQ-VER-002`
- **Decisions:** `D-10-01`, `D-10-02` (2026-11-21 quality audit)

> **Correction note (2026-11-21 re-execution):** earlier revisions of this
> report referenced a nonexistent test file
> `tests/nlp/test_phase10_nlp_and_injection.py` (actual files:
> `tests/nlp/test_multilingual_and_robustness.py`,
> `tests/nlp/test_phase10_text_layer.py`, `tests/scoring/test_explanation_linter.py`),
> omitted task 10.6 from the machine-readable task matrix, and cited phantom
> requirement `REQ-SCORE-020` (not defined in Master TZ v3.0.0; scoring
> requirements end at `REQ-SCORE-005`). All corrected below.

## Sessions

| Session | Branch | Base → End commit | Outcome |
| --- | --- | --- | --- |
| Initial implementation (Phase 10–11 batch) | `arena/3a99279e-genesis-hackathon-malika-nurzh` | `da42d26` → (merged via PR #11 as `7f47638`) | DONE |
| Quality audit & gap closure (this report) | `arena/794acafe-genesis-hackathon-malika-nurzh` | `7f47638` → see `docs/AGENT_REPORTS/2026-11-21/arena-phase-10-audit.md` | DONE |

## Task Matrix (Master TZ §24, Phase 10)

| Task | Requirement IDs | Status | Evidence |
| --- | --- | --- | --- |
| 10.1 Deterministic ru/kk/en templates | REQ-NLP-001, REQ-PROD-020 | DONE | `gen/core/text.py` (`_SERVICE_TEMPLATES`, `_BANK_REF_TEMPLATES`, `_JE_*`, `_CN_REASON_TEMPLATES`), isolated `text_layer` RNG stream, pinned `TEXT_LAYER_VERSION` / `TEMPLATE_DICTIONARY_VERSION` recorded in provenance; `tests/nlp/test_phase10_text_layer.py::TestPhase10DeterministicTemplates` |
| 10.2 Abbreviations, transliteration, benign typos | REQ-NLP-001, REQ-NLP-005 | DONE | business abbreviations in templates (`сч/ф`, `Пл. пор.`, `Pmt inv.`, `ш/ф`, `ТТК`), `_apply_controlled_ocr_noise` (protected typed IDs never perturbed), `nlp/normalize.py::transliterate_to_ascii_skeleton`; `TestPhase10AbbreviationsTyposTransliteration` |
| 10.3 Unicode normalization tests | REQ-NLP-005 | DONE | `tests/unit/test_property.py::test_unicode_nfc_and_skeleton_idempotence_property`, `::test_text_similarity_and_ngrams_unicode_stability_property`, `TestPhase10UnicodeNormalization` (zero-width/bidi stripping, NFD→NFC, homoglyph typed-ID rejection, NFC of all emitted text) |
| 10.4 Text-to-entity candidate matching (optional helper) | REQ-NLP-002, REQ-ARC-001 | DONE | `nlp/matching.py` (`CandidateMatch` always `requires_structural_verification=True`, hypothesis tier only); optionality proven by `TestPhase10OptionalEntityMatching` (core loads zero `nlp` submodules; scorer loads only `nlp.hierarchy`) + AST granular rule in `tools/check_import_boundaries.py` |
| 10.5 Evidence hierarchy & no text-only findings | REQ-NLP-002, REQ-SCORE-001 | DONE | `nlp/hierarchy.py` (`assess_evidence_support`, `assess_evidence_reachability`, `build_evidence_hierarchy_report`, `require_structural_proof` → `TextOnlyProofRejectedError`); enforcement wired into `scoring/scorer_cli.py` (`diagnostics.evidence_hierarchy`); `TestPhase10EvidenceHierarchyEnforcement` (text-only finding → tier-4 inadmissible + `evidence_incomplete` + zero reward) |
| 10.6 Explanation consistency linter + report | REQ-NLP-002 | DONE | `scoring/explanation_linter.py` (5 rules EC-01..EC-05 per TZ §17.6, diagnostic-only); deliverable artifact `tools/explanation_report.py` → `artifacts/reports/latest/explanation_consistency_report.json`; `tests/scoring/test_explanation_linter.py`, `TestPhase10ExplanationConsistencyReport` |

## Deliverables (Master §24 "Результаты")

- `gen/core/text.py` — deterministic multilingual text layer (kept as module, not package `gen/core/text/`; see `D-10-02`).
- `nlp/` — `normalize.py`, `matching.py`, `hierarchy.py`, `injection_guard.py` (lazy facade `__init__.py`).
- **Explanation consistency report** — `tools/explanation_report.py` writing `artifacts/reports/latest/explanation_consistency_report.json` (regenerable, gitignored).

## EXIT GATE 10 — Verification

> Gate text: *«текстовый слой отключается без влияния на core; verifier does not
> rely on unsupported fuzzy matches»*

| Gate item | Status | Evidence |
| --- | --- | --- |
| Text layer disableable without affecting core | PASS | `tests/generator/test_rng_isolation.py::test_text_and_injection_namespaces_never_change_amounts_ids_or_truth` — `enable_text_layer` on/off × 4 language profiles × noise 0–2 × injection toggle produce byte-identical `sealed/truth.json`, invoice signatures and `verifier.discover` findings; `TestPhase10DeterministicTemplates` proves same-seed byte-identical text and pinned dictionary versions |
| Verifier does not rely on unsupported fuzzy matches | PASS | AST import-boundary rule (`verifier` forbids `nlp` top-level — `tools/check_import_boundaries.py`, `make lint` → `CLEAN`); granular rule forbids fuzzy helpers anywhere in `scoring/` (only `nlp.hierarchy` allowed); `TestPhase10OptionalEntityMatching::test_core_modules_load_no_nlp_submodules` proves `verifier`, `env`, `gen`, `harness`, `seal`, matcher/reward/diagnostics load **zero** `nlp` code |

## Command Log (2026-11-21 audit session)

| Command | Exit | Status | Result |
| --- | --- | --- | --- |
| `python3 -m unittest discover -s tests -t .` | 0 | PASS | 343 tests OK (baseline before session: 316 OK) |
| `python3 -m unittest tests.nlp.test_phase10_text_layer` | 0 | PASS | 23 tests OK |
| `python3 -m unittest tests.unit.test_property` | 0 | PASS | 8 property suites OK |
| `python3 -m unittest tests.unit.test_import_boundaries` | 0 | PASS | 9 tests OK |
| `make lint` (compile + AST boundary scan) | 0 | PASS | `import boundary scan: CLEAN (REQ-ARC-001..007)` |
| `python3 judge/robustness_audit.py` (RC-006) | 0 | PASS | pairs=4 → `artifacts/reports/latest/robustness_report.json` |
| `python3 tools/explanation_report.py --demo --output artifacts/reports/latest/explanation_consistency_report.json` | 0 | PASS | 5 findings checked (2 consistent, 3 intentionally inconsistent) |

## Known Limitations / Notes

- `nlp/` fuzzy helpers (n-gram/TF-IDF-style similarity) remain **optional** priority-C features (TZ §25.3); no model/sklearn dependency is required (`text_similarity_bps` is integer basis-point stdlib only).
- The evidence-hierarchy block in `scoring/scorer_cli.py` is **diagnostic-only** by design (TZ §15.9): reward/matching semantics are untouched (`D-06-05` preserved).
- Prompt-injection robustness payloads live in `gen/core/text.py::BENIGN_INJECTION_TEMPLATES` and are evaluated by the Phase 11 track (`judge/robustness_audit.py`, `configs/robustness/default.json`), which is off by default for official scoring (REQ-NLP-004).

## Readiness for Next Phase

Phase 10 deliverables are complete; Phase 11 (robustness track) inputs it depends on (`BENIGN_INJECTION_TEMPLATES`, `nlp/injection_guard.py`, `injection_layer` RNG stream) are present and green (RC-006 PASS).
