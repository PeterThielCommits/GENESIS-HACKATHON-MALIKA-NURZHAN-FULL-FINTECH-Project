# CHANGELOG

Format: [Keep a Changelog](https://keepachangelog.com/) style, versions follow
`contracts/version.json` for contracts and an independent repository version for code.

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
