# ARCHITECTURE SNAPSHOT — what actually exists at end of Phase 0

This is a *state* snapshot, not a plan. Planned architecture: `docs/DESIGN.md`.

```
repo root
├── contracts/          [IMPLEMENTED]  12 schemas + 35 fixtures + CONTRACT.md + registries
│   └── fixtures/                       35 cases: valid/invalid with expected JSON pointers
├── configs/            [IMPLEMENTED]  generator, environment (limits/mode/cursor/resources),
│                                       scoring (reward/match/tolerance), arena, rubric, adapter
├── spec/               [CATALOG ONLY] anomaly_catalog.json (4 types, 16 distractors),
│                                       invariants.json (INV-01..INV-17)
├── adapter/            [UNBOUND]      compatibility profile + organizer entry points that
│                                       raise ADAPTER_NOT_BOUND / ADAPTER_VERSION_UNSUPPORTED
├── tools/              [IMPLEMENTED]  canonical_json, jsonschema_lite, validate_contracts,
│                                       extract_requirements, check_import_boundaries,
│                                       check_governance, check_setup, verify
├── judge/              [MAP ONLY]     rubric_map.json — 40 internal checks, official:false
├── tests/              [IMPLEMENTED]  unit/ (canonical JSON, adapter, configs),
│                                       contracts/ (fixtures, self-consistency),
│                                       phase0/ (assumptions, questions, decisions, rubric,
│                                       contract docs, claims, data policy, archive, report)
├── docs/               [IMPLEMENTED]  context, decisions, questions, status, risk, threat
│                                       model, limitations, independence, data dictionary,
│                                       design, rubric traceability, policy, reports
└── (missing)           gen/ invariants/ verifier/ env/ harness/ scoring/ seal/ arena/
                        metamorphic/ episodes/   → Phases 2–13
```

## Data flow that exists today

```
contracts ──► tools/validate_contracts ──► artifacts/reports/latest/contracts_report.json
configs   ──► assumption cross-checks   ──► tests/unit/test_*_config.py
docs      ──► tools/check_governance    ──► artifacts/reports/latest/governance_report.json
*.py      ──► tools/check_import_boundaries ──► .../import_boundaries_report.json
           ──► tools/verify             ──► artifacts/reports/latest/verify_summary.{json,txt}
                                              artifacts/reports/latest/rubric_matrix.csv
```

There is **no episode, no environment, no scorer and no reward computation** yet. Any diagram
suggesting otherwise would be a false claim.

## Trust boundaries that exist today

| Boundary | Implemented today |
|----------|-------------------|
| Git ↔ sealed data | `.gitignore` + governance check (enforced) |
| Reports ↔ secrets | claim/secret scan in `GOV-CLAIMS-01` (enforced) |
| Internal ↔ external contract | `adapter/` unbound, fails closed (enforced) |
| Module zones | AST import-boundary scan with the full §6 table (enforced) |
| policy ↔ env ↔ scorer | **not implemented** — Phase 5/8 |
| OS sandbox | **not implemented and not claimed** |
