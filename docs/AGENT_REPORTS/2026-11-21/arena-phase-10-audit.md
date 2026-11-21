# Arena agent — Phase 10 quality audit & gap-closure session (2026-11-21)

**PHASE:** 10 — MULTILINGUAL TEXT / NLP LAYER (Master TZ §24)
**STATUS:** DONE
**Agent ID:** arena-agent (Arena.ai Agent Mode), human owner: Malika/Nurzhan (hackathon team)
**Master TZ:** v3.0.0 `docs/reference/TwinLedger_v3_Master_TZ_AI_Agents.txt`,
sha256 `a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36`
(verified identical to the uploaded working copy).

## 1. Context loaded

`AGENTS.md`, `docs/PROJECT_CONTEXT.md`, `docs/CURRENT_STATE.md`,
`docs/DECISIONS.md`, `docs/STATUS.md`, `docs/QUESTIONS.md`,
`docs/PHASE_REPORTS/PHASE-10.{md,json}`, `docs/CONTEXT/NEXT_AGENT.md`,
Master TZ §17 + §24 + §25, `contracts/finding.schema.json`, `gen/core/text.py`,
`nlp/*`, `scoring/{canon,matcher,reward,diagnostics,explanation_linter,scorer_cli}.py`,
`tools/check_import_boundaries.py`, tests for `nlp/`, `scoring/`, `generator/`,
`unit/`.

## 2. Goal and requirements

Re-execute Phase 10 per the Universal Phase Execution Prompt (`PHASE_NUMBER=10`):
audit the previously-claimed DONE state at high quality, close real gaps, and
re-verify EXIT GATE 10 («текстовый слой отключается без влияния на core; verifier
does not rely on unsupported fuzzy matches»). REQ IDs: `REQ-NLP-001..005`,
`REQ-PROD-020`, `REQ-ARC-001`, `REQ-VER-002`.

## 3. Baseline (pre-session, start commit `7f47638276ccf6b12525dceffdd3b9e2842d4f37`)

- Branch `arena/794acafe-genesis-hackathon-malika-nurzh` (from `main` @ merge of PR #11), clean tree.
- `python3 -m unittest discover -s tests -t .` → **316 tests OK** (all green before any change).
- Phase 10 audit classification before this session:
  10.1 IMPLEMENTED-UNVERIFIED (no dictionary version pinning, no determinism test);
  10.2 IMPLEMENTED-UNVERIFIED (no typo/abbreviation tests);
  10.3 VERIFIED (minor gaps: no zero-width/bidi/homoglyph cases);
  10.4 VERIFIED (missing optionality proof);
  10.5 PARTIAL (hierarchy module existed but was wired into **no** production path);
  10.6 PARTIAL (linter existed; the named deliverable «explanation consistency
  report» artifact was missing);
  docs DEFECTIVE (`PHASE-10.md/json` referenced nonexistent
  `tests/nlp/test_phase10_nlp_and_injection.py`, omitted task 10.6 in JSON, and
  cited phantom `REQ-SCORE-020`).

## 4. Implementation (this session)

- `nlp/hierarchy.py`: added `assess_evidence_reachability` (tier verdict from
  structural public reachability only) and `build_evidence_hierarchy_report`
  (per-finding diagnostic block); single tier vocabulary shared with
  `assess_evidence_support`; fixed TZ section refs (§11.x → §17.x).
- `scoring/scorer_cli.py` + `scoring/diagnostics.py`: evidence-hierarchy
  enforcement wired into the official scoring path as
  `diagnostics.evidence_hierarchy` (diagnostic-only; reward untouched).
- `nlp/__init__.py`: converted to a lazy PEP-562 facade — `scorer_cli`'s
  strict-rule import loads **only** `nlp.hierarchy`; core loads zero `nlp`
  submodules.
- `gen/core/text.py`: pinned `TEXT_LAYER_VERSION` / `TEMPLATE_DICTIONARY_VERSION`
  (TZ §17.2 «фиксированные версии словарей») recorded in generation provenance;
  docstring refs fixed.
- `tools/explanation_report.py` (**new deliverable**): deterministic
  explanation-consistency report generator (rules EC-01..EC-05, demo corpus +
  submission mode) → `artifacts/reports/latest/explanation_consistency_report.json`.
- `tools/check_import_boundaries.py`: granular rules — `verifier`/`gen`/`env`/
  `seal`/`harness`/`core`/`invariants` may not import `nlp` at all;
  `scoring/` may import only `nlp.hierarchy` from `nlp` (fuzzy helpers
  machine-forbidden).
- **New tests** (`tests/nlp/test_phase10_text_layer.py`, 23 cases): same-seed
  byte-identical text, dictionary version pinning, abbreviation presence,
  deterministic OCR typos with protected typed IDs byte-exact, transliteration
  skeletons, zero-width/bidi stripping, NFD→NFC, homoglyph typed-ID rejection,
  NFC property of all emitted text, hypothesis-tier-only candidate matches,
  subprocess optionality proofs, evidence-hierarchy tier mapping, text-only
  finding → `TextOnlyProofRejectedError` + `evidence_incomplete` + zero reward,
  diagnostics passthrough, explanation report correctness.
- `tests/unit/test_property.py`: +1 Unicode-stability property over
  `text_similarity_bps` / `char_ngrams` (REQ-NLP-005 completeness).
- `tests/unit/test_import_boundaries.py`: +3 negative/positive tests for the
  new granular rules.

## 5. Verification (exact commands & exit codes)

| Command | Exit | Status | Result |
| --- | --- | --- | --- |
| `python3 -m unittest discover -s tests -t .` | 0 | PASS | 343 tests OK (baseline 316) |
| `python3 -m unittest tests.nlp.test_phase10_text_layer -v` | 0 | PASS | 23/23 |
| `python3 -m unittest tests.unit.test_property -v` | 0 | PASS | 8/8 |
| `python3 -m unittest tests.unit.test_import_boundaries -v` | 0 | PASS | 9/9 |
| `make lint` | 0 | PASS | `import boundary scan: CLEAN (REQ-ARC-001..007)` |
| `python3 judge/robustness_audit.py` (RC-006) | 0 | PASS | pairs=4, truth digests & verifier reports identical across language variants |
| `python3 tools/explanation_report.py --demo --output artifacts/reports/latest/explanation_consistency_report.json` | 0 | PASS | 5 findings (2 consistent / 3 intentionally inconsistent) |

Failed/skipped/not-run: none. Optional extras (Hypothesis/sklearn) SKIPPED by
design — stdlib fallback property loops cover REQ-NLP-005; no impact on EXIT GATE.

## 6. Files created / modified

- Created: `tests/nlp/test_phase10_text_layer.py`, `tools/explanation_report.py`
- Modified: `gen/core/text.py`, `nlp/__init__.py`, `nlp/hierarchy.py`,
  `nlp/matching.py`, `nlp/normalize.py`, `scoring/scorer_cli.py`,
  `scoring/diagnostics.py`, `tools/check_import_boundaries.py`,
  `tests/unit/test_import_boundaries.py`, `tests/unit/test_property.py`,
  `docs/PHASE_REPORTS/PHASE-10.md`, `docs/PHASE_REPORTS/PHASE-10.json`,
  `docs/DECISIONS.md`, `docs/CURRENT_STATE.md`, `docs/STATUS.md`,
  `docs/CONTEXT/NEXT_AGENT.md`
- Deleted: none
- Contracts/API touched: **none** (no frozen schema change). Diagnostics output
  gains one additive key `evidence_hierarchy` (internal diagnostics schema
  `x_twinledger_internal_diagnostics/0.1.0`, non-reward-affecting; an approved-CR
  question is NOT required — diagnostics is explicitly out of reward per TZ §15.9).

## 7. Decisions

- **D-10-02** (appended to `docs/DECISIONS.md`): module-vs-package deviation
  (`gen/core/text.py` instead of `gen/core/text/`), pinned dictionary versions,
  lazy `nlp` facade, scorer-side hierarchy enforcement via `nlp.hierarchy` only,
  explanation-consistency report tool, and `REQ-SCORE-020` phantom-ID removal.

## 8. Known issues / risks

- None blocking. Note: `nlp` fuzzy helpers remain priority-C optional features
  (TZ §25.3) and are not part of any reward path.

## 9. GitHub traceability

- Branch: `arena/794acafe-genesis-hackathon-malika-nurzh`; start commit
  `7f47638276ccf6b12525dceffdd3b9e2842d4f37`; end commit: the commit containing
  this report (hash recorded in the PR body).
- PR/Issue links appended below once published.

## 10. Next action

Next phase per plan (Phase 11 re-audit or clean-clone `make verify`) — see
`docs/CONTEXT/NEXT_AGENT.md`. Owner: Zone D (docs/QA) + Zone A (generator) for
any follow-ups.
