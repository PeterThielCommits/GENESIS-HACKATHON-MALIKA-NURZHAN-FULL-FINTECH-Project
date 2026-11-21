# Architecture Snapshot (Phase 8)

```
contracts/   schemas + canonical + models + validator + currency (frozen v1.0.0)
adapter/     organiser protocol adapter (Phase 5+, provisional A-*)
gen/         clean twins + operators + diff truth (Phase 3-4, 7, Zone 1)
spec/        normative accounting rules + frozen verifier_algorithm.md (v1.0.0)
invariants/  INV-01..INV-17 checks (Phase 2)
verifier/    independent public-only discovery + ProofGraph + ablation (Phase 8, Zone 3)
env/         reset/step + tools (Phase 5, Zone 2)
harness/     JSONL + trajectory + replay (Phase 9, Zone 2)
scoring/     canon + matcher + reward + diagnostics + exhaustive + crosscheck (Phase 6 & 8, Zone 2)
seal/        commit-reveal + Merkle + receipts (Phase 9, Zone 2)
arena/       baselines + attacks (Phase 12, Zone 3)
metamorphic/ M-01..M-07 (Phase 13)
judge/       verify CLI + rubric map + reports (Phase 14, Zone 4)
tools/       dataset/inspect/manifest/boundaries/freeze
configs/     versioned configs (generator/environment/scoring/arena/rubric)
tests/       unit + contracts + scoring + generator + verifier (Phase 8: 197 + 3 property tests)
episodes/    train/dev (+ hidden, git-ignored sealed)
docs/        context, tasks, handoffs, phase reports, agent reports, CR, INDEPENDENCE.md
```

Phase 8 verifier internals (Zone 3, `contracts/` + Python 3.11 stdlib only;
zero `gen/`, `core/`, `invariants/`, or `scoring/` imports):
`public_loader.py` allowlisted public loader + canonical `episode_public_hash` +
`subset_public_episode()`; `money_time.py` independent exact `Fraction` FX
conversion (direct & inverse ISO pairs) and `ZoneInfo` fiscal periods;
`proof_graph.py` deterministic 5-node/5-edge ProofGraph DAG + acyclicity &
traceability validation; `duplicate_payment.py`, `partial_allocation.py`,
`fx_mismatch.py`, `period_cutoff.py` independent detectors + 16 minimum
distractor exclusions (`D-DUP/PART/FX/CUT-01..04`); `evidence.py` public-tool
reachability + `max_evidence_ids`; `minimal_sets.py` sufficiency + greedy
minimizer + single-element/full-set deletion ablation; `validate.py`,
`discover.py`, `__main__.py` Stage-1 discovery + pre-committed `report_digest`.

Phase 6 + Stage-2 Phase 8 scoring internals (Zone 2, `contracts/` + stdlib only):
`canon.py`, `matcher.py`, `reward.py`, `diagnostics.py`, `exhaustive.py`, and
`crosscheck.py` (Stage-2 post-discovery verification against sealed truth with
`report_digest` lock, non-union per-set evidence matching, exact `Fraction`
TZ §13.7 metrics, and `release_blocked` gating).

Import rules (machine-checked): `env` ↛ gen/verifier/scoring/seal;
`verifier` ↛ gen (and AST-checked ↛ core/invariants/scoring/env/harness/seal/arena);
`arena/policies|attacks` ↛ private internals;
`scoring` → contracts/seal (↛ gen/verifier/env/harness); `seal` → contracts/stdlib;
`gen` ↛ verifier/scoring/seal; `harness` ↛ gen/verifier/scoring/seal.
