# Architecture Snapshot (Phase 1)

```
contracts/   schemas + canonical + models + validator (frozen v1.0.0)
adapter/     organiser protocol adapter (Phase 5+, provisional A-*)
gen/         clean twins + operators + diff truth (Phase 3-4, Zone 1)
spec/        normative accounting rules (shared spec only)
invariants/  INV-01..INV-17 checks (Phase 2)
verifier/    public-only discovery + ProofGraph (Phase 8, Zone 3)
env/         reset/step + tools (Phase 5, Zone 2)
harness/     JSONL + trajectory + replay (Phase 9, Zone 2)
scoring/     matcher + reward (Phase 6, Zone 2)
seal/        commit-reveal + Merkle + receipts (Phase 9, Zone 2)
arena/       baselines + attacks (Phase 12, Zone 3)
metamorphic/ M-01..M-07 (Phase 13)
judge/       verify CLI + rubric map + reports (Phase 14, Zone 4)
tools/       dataset/inspect/manifest/boundaries/freeze
configs/     versioned configs (generator/environment/scoring/arena/rubric)
tests/       unit + contracts (Phase 1); gen/verifier/env/... later
episodes/    train/dev (+ hidden, git-ignored sealed)
docs/        context, tasks, handoffs, phase reports, agent reports, CR
```

Import rules (machine-checked): `env` ↛ gen/verifier/scoring/seal;
`verifier` ↛ gen; `arena/policies|attacks` ↛ private internals;
`scoring` → contracts/seal; `seal` → contracts/stdlib;
`gen` ↛ verifier/scoring/seal; `harness` ↛ gen/verifier/scoring/seal.
