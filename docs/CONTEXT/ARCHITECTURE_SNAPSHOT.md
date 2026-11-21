# Architecture Snapshot (Phases 1–8 Integrated)

```
contracts/   schemas + canonical + models + validator + currency (frozen v1.0.0)
adapter/     provisional organiser protocol adapter (Phase 5, A-*)
core/        exact money + company-local time + anti-shortcut IDs (Phase 2)
invariants/  INV-01..INV-17 group checks (Phase 2)
gen/         Clean Twin + 16 distractors + all 4 operators + diff truth + serializer (Phases 3, 4, 7, Zone 1)
spec/        normative accounting rules + frozen verifier_algorithm.md (v1.0.0)
verifier/    independent public-only discovery + ProofGraph + ablation + CLI (Phase 8, Zone 3)
env/         public-only reset/step + tools + safe AST calc + HMAC cursors + JSONL server (Phase 5, Zone 2)
harness/     JSONL + trajectory + replay (Phase 9, Zone 2)
scoring/     canon + matcher + reward + diagnostics + exhaustive + Stage-2 crosscheck (Phases 6 & 8, Zone 2)
seal/        commit-reveal + Merkle + receipts (Phase 9, Zone 2)
arena/       baselines + attacks (Phase 12, Zone 3)
metamorphic/ M-01..M-07 (Phase 13)
judge/       verify CLI + rubric map + reports (Phase 14, Zone 4)
tools/       make_dataset (with Stage-1/Stage-2 gate) + verify_manifest + inspect_episode + check_import_boundaries
configs/     versioned configs (generator/environment/scoring/arena/rubric)
tests/       contracts + unit + generator + env + scoring + verifier (214 + 3 property tests)
episodes/    dev (6 verified) + train (4 verified); sealed/ strictly gitignored
docs/        context, CR (CR-06-01 resolved), phase reports, agent reports, INDEPENDENCE.md
```

Import rules (machine-checked by `tools/check_import_boundaries.py`):
- `env` ↛ gen/verifier/scoring/seal (and zero private path literals)
- `verifier` ↛ gen (and AST-checked ↛ core/invariants/scoring/env/harness/seal/arena; zero private path literals)
- `arena/policies|attacks` ↛ private internals
- `scoring` → contracts/seal only (↛ gen/verifier/env/harness)
- `seal` → contracts/stdlib only
- `gen` ↛ verifier/scoring/seal
- `harness` ↛ gen/verifier/scoring/seal
