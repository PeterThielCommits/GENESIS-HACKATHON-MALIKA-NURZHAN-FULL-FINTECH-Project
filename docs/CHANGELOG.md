# TwinLedger — Changelog

## 0.1.0 — Phase 1 (2026-11-20)

- Repository skeleton per Master TZ 6; Python 3.11 stdlib-only core.
- Contracts frozen v1.0.0: 12 JSON schemas + `version.json` +
  `currency.json`; canonical JSON; typed models; stdlib validator.
- Import-boundary scanner (`tools/check_import_boundaries.py`).
- Makefile targets, CI workflow, PR/issue templates, CODEOWNERS.
- Versioned configs (generator/environment/scoring/arena/rubric).
- Normative spec skeletons (`spec/`), provisional rubric map.
- 34 passing tests; `make verify-core` PASS.
- Full Phase 1 docs set (`docs/`).

## Unreleased

- Phase 2: money/time/ID/invariant primitives.
