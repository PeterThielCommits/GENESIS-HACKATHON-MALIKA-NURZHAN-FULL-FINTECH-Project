# CHANGELOG

Format: [Keep a Changelog](https://keepachangelog.com/) style, versions follow
`contracts/version.json` for contracts and an independent repository version for code.

## [Unreleased] — 2026-11-20 — Phase 1 foundation

### Added
- `models/` — 11 typed dataclasses mirroring the schemas, with construction-time validation,
  `x_` extension preservation and `canonical()` as the only serialisation hinge.
- `tools/check_models.py`, `tools/check_golden.py`, `tools/check_ci.py`, `tools/probe_starter.py`.
- `contracts/GOLDEN.json` — per-file freeze hashes plus payload and fixture digests.
- `.github/workflows/verify.yml`, `pull_request_template.md`, 4 issue forms, `CODEOWNERS`.
- `docs/BRANCH_PROTECTION.md`, `docs/PHASE0_CHECKLIST.md`, `docs/PHASE_REPORTS/PHASE-01.md`.
- `configs/submission/{submission,starter_probe}.json`, `docs/official/SUBMISSION_DEADLINE.md`.
- 5 rubric checks: `CT-GOLDEN-01`, `EN-MODELS-01`, `EN-CI-01`, `EN-SUBMIT-01`, `EN-PROBE-01`
  (45 internal checks total, 17 implemented).
- 3 governance checks: `GOV-CI-01`, `GOV-DEADLINE-01`, `GOV-MODELS-01` (16 total).
- Decisions D-0021…D-0024; tests under `tests/phase1/`.

### Changed
- `tools/verify.py` runs models/golden/CI/probe, emits 12 artifacts and generates both
  `PHASE-00.json` and `PHASE-01.json` from its own summary.
- `tools/check_import_boundaries.py` understands the new `models/` zone.
- `tools/validate_contracts.contract_digest()` excludes the freeze metadata, so the schema payload
  digest is stable across a golden refresh.

## [Unreleased]

### Added

* Repository foundation for Phase 0: contracts v0.1.0, configs, adapter boundary, tooling,
  governance documents, Phase 0 report.
* `tools/canonical_json.py`, `tools/jsonschema_lite.py`, `tools/validate_contracts.py`,
  `tools/extract_requirements.py`, `tools/check_import_boundaries.py`,
  `tools/check_governance.py`, `tools/verify.py`, `tools/check_setup.py`.
* Contracts: 12 schemas (11 typed documents + shared definitions), 35 fixtures, version and
  currency registries, human-readable `contracts/CONTRACT.md`.
* `configs/`: generator, environment (limits, mode, cursor, resources), scoring (reward,
  match, tolerance), arena, rubric, adapter compatibility.
* `spec/`: anomaly catalog (4 types, 16 distractors) and invariant catalog (17 invariants).
* `docs/`: project context, current state, status, decisions (D-0001…D-0020), questions
  (Q-001…Q-014 + OPEN-0), assumptions registry, requirements registry (186 requirements),
  risk register, threat model, limitations, independence, data dictionary, design, ownership,
  Git/data policy, rubric traceability, phase report.
* `judge/rubric_map.json`: 39 internal checks across five provisional blocks, all
  `official: false`.

### Changed

* Nothing pre-existing: the repository contained only `README.md` at branch point `c961a00`.

### Security

* Sealed/hidden/generated data excluded from Git (D-0008) with an enforced check.
* Automated claim scan blocks "official score"/"100/100"/guaranteed-win statements (R-24).
* Literal salt/seed values in tracked text are a release blocker.

## [0.1.0] — 2026-11-20

Phase 0 baseline: contract freeze candidate, no runtime yet. See
`docs/PHASE_REPORTS/PHASE-00.md` for executed commands and results.
