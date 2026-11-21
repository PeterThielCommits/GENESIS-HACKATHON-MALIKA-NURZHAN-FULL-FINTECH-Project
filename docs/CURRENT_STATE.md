# Current State

- **Active branch:** `arena/794acafe-genesis-hackathon-malika-nurzh` (from `main` @ `7f47638` = merge of PR #11).
- **Completed Master TZ phases:** **Phases 0–17 COMPLETE (100%)**, with **Phase 10 re-executed at full depth (2026-11-21 quality audit, `D-10-02`)** and **code-review remediation applied (`D-10-03`: verbatim row-order loading + bounded episode-input reads, limitation `L7`)**.
- **Current test baseline:** `python3 -m unittest discover -s tests -t .` → **354 tests OK**; `make lint` → `CLEAN (REQ-ARC-001..007)`; `make test-official` → 55/55 (incl. `P01..P20` paired invariance); `make replay` → byte-identical.
- **Phase 10 audit outcome (this branch):** tasks 10.1–10.6 all DONE against Master TZ §24/§17:
  - 10.1: deterministic ru/kk/en/mixed templates in `gen/core/text.py` with pinned `TEXT_LAYER_VERSION`/`TEMPLATE_DICTIONARY_VERSION` (recorded in provenance) + same-seed byte-identical determinism tests.
  - 10.2: business abbreviations, transliteration (`nlp/normalize.py`), benign OCR typos with protected typed IDs byte-exact (`_apply_controlled_ocr_noise`) + tests.
  - 10.3: Unicode normalization tests incl. zero-width/bidi stripping, NFD→NFC, homoglyph typed-ID rejection, NFC property of emitted text, Unicode-form-invariant similarity (`tests/unit/test_property.py`).
  - 10.4: text-to-entity candidate matching as optional hypothesis-tier helper (`nlp/matching.py`), with subprocess proof that core loads zero `nlp` submodules.
  - 10.5: evidence hierarchy ENFORCED — `nlp/hierarchy.py::assess_evidence_reachability` + `build_evidence_hierarchy_report` wired into `scoring/scorer_cli.py` (`diagnostics.evidence_hierarchy`, diagnostic-only); text-only findings provably inadmissible and reward-less.
  - 10.6: explanation consistency linter (`scoring/explanation_linter.py`) + **report artifact** `tools/explanation_report.py` → `artifacts/reports/latest/explanation_consistency_report.json`.
  - EXIT GATE 10 PASS (text layer off ⇒ core byte-identical; verifier/scoring rely on no fuzzy matches — AST rules + subprocess import tests).
- **Review remediation (2026-11-21, `D-10-03`):** `env/loader.py` now preserves file row order verbatim (README "Canonical Tables"; the old pk-sort was an identity operation on generated episodes and is now removed for external/permutation inputs); all episode-supplied reads (`env/loader.py`, `adapter/official_env.py`, `scoring/official_scorer.py`, `verifier/public_loader.py`) are byte/row-capped via `contracts.loader.read_text_bounded`/`check_row_cap` (16 MiB / 100 000 rows, `LIMIT` errors; limitation `L7`). Locked by `tests/env/test_loader_order_and_bounds.py` (11 tests).
- **Phase 9 Risk Remediation (`P-012`/`R-09`, `L4`, `L5`):** COMPLETE (kernel `user+mount+net` namespaces + `seccomp-BPF`, CSPRNG rekey, Stage-2 semantic truth verification).
- **Phases 11–17 summary (unchanged):** robustness track (`judge/robustness_audit.py`, RC-006 PASS pairs=4), 22-attack Arena + AutoHacker + shortcut audit (`macro_ROC_AUC=0.5389<=0.55`), metamorphic `M-01..M-07` + 26/26 mutants killed, 12-gate Judge Kit (`RC-001..RC-012`), offline HTML report, 3-minute deterministic jury demo, cryptographic release freeze (30 files).
- **Active blockers:** None.
- **Next actions (exactly three):**
  1. Merge PR #12 (Phase 10 audit + review remediation) after CI green — owner: team lead.
  2. Run `make verify` on a clean clone to re-confirm `RC-001..RC-012` against the audit + remediation changes — owner: Zone D (QA).
  3. Proceed to Phase 11 re-audit or submission prep per `docs/CONTEXT/NEXT_AGENT.md` — owner: orchestrator.
