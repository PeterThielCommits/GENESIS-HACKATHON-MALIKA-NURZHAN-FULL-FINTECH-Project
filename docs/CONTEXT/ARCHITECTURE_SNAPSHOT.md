# Architecture Snapshot (Phase 6)

```
contracts/   schemas + canonical + models + validator (frozen v1.0.0)
adapter/     organiser protocol adapter (Phase 5+, provisional A-*)
gen/         clean twins + operators + diff truth (Phase 3-4, Zone 1)
spec/        normative accounting rules (shared spec only)
invariants/  INV-01..INV-17 checks (Phase 2)
verifier/    public-only discovery + ProofGraph (Phase 8, Zone 3)
env/         reset/step + tools (Phase 5, Zone 2)
harness/     JSONL + trajectory + replay (Phase 9, Zone 2)
scoring/     canon + matcher + reward + diagnostics + exhaustive (Phase 6, Zone 2)
seal/        commit-reveal + Merkle + receipts (Phase 9, Zone 2)
arena/       baselines + attacks (Phase 12, Zone 3)
metamorphic/ M-01..M-07 (Phase 13)
judge/       verify CLI + rubric map + reports (Phase 14, Zone 4)
tools/       dataset/inspect/manifest/boundaries/freeze
configs/     versioned configs (generator/environment/scoring/arena/rubric)
tests/       unit + contracts + scoring (Phase 6: 131 tests)
episodes/    train/dev (+ hidden, git-ignored sealed)
docs/        context, tasks, handoffs, phase reports, agent reports, CR
```

Phase 6 scoring internals (Zone 2, contracts + stdlib only):
`canon.py` typed-ID canonicalisation + boundary validation;
`matcher.py` predicate (TZ 15.2) + three-level optimal matching
(TZ 15.3, single source of TP/FP/FN); `reward.py` exact rational
F1/reward (TZ 15.4-15.6); `diagnostics.py` TZ 15.8/15.9 payload +
P1..P5 property matrix; `exhaustive.py` brute-force differential
oracle (<=7x7).

Import rules (machine-checked): `env` ↛ gen/verifier/scoring/seal;
`verifier` ↛ gen; `arena/policies|attacks` ↛ private internals;
`scoring` → contracts/seal; `seal` → contracts/stdlib;
`gen` ↛ verifier/scoring/seal; `harness` ↛ gen/verifier/scoring/seal.
