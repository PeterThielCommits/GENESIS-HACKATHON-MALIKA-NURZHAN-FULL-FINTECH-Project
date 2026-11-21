# TwinLedger — Project Context (for new agents)

## Mission

TwinLedger is a proof-oriented, RL-compatible benchmark for AI agents
that audit synthetic accounting data through a limited tool set. Each
episode is a fictional company with invoices, payments, bank lines,
journal entries, FX rates, accounting policy and documents. Some episodes
are clean; others contain one or more controlled accounting anomalies.
The agent inspects only public records within a step budget and submits
structured findings.

Two duties:

- **Environment**: honest, deterministic, limited research interface.
  Never reveals hidden labels, provenance, seed, mutation params or
  scorer internals.
- **Evaluator**: checks findings against sealed truth, evidence
  sufficiency and reward. Inaccessible during an active episode.

Core idea: *counterfactual twins + independent verifier + proof-carrying
episodes + sealed evaluation + adversarial reward assurance + reproducible
benchmark toolkit.*

## Official vs provisional

The official organiser TZ/rubric has **not** been published in this repo
(Phase 0 incomplete). Everything from Master TZ assumptions A-001…A-016
(tool names, 4 anomaly types, reward `R = max(0, F1 − 0.05·steps/100)`,
100-step budget, 50 page size) is **provisional** and isolated in
`adapter/` + `configs/`. See `docs/DECISIONS.md`, `docs/QUESTIONS.md`,
`docs/RUBRIC_TRACEABILITY.md`. Never present provisional values as
official facts.

## Architecture & trust boundaries

- `gen/` (Zone 1): clean twins, mutation operators, diff-derived truth.
- `spec/` + `invariants/`: normative accounting rules (shared spec only).
- `verifier/` (Zone 3): independent public-only discovery + ProofGraph.
  Must not import `gen/` (REQ-VER-002).
- `env/` (Zone 2): public-only loader, reset/step, tools, budget.
  Must not import gen/verifier/scoring/seal (REQ-ARC-002).
- `harness/` (Zone 2): JSONL mediation, trajectory, replay.
- `scoring/` + `seal/` (Zone 2): matcher, reward, commit-reveal, receipts.
  Scorer runs only after env closes (REQ-ARC-005).
- `arena/` (Zone 3): baselines/attacks via public API only.
- `judge/` (Zone 4): `make verify`, rubric map, reports.

Data flow (build): RNG namespaces → clean C → operators → M; diff(C,M) →
candidate truth; verifier reads only M/public → findings; cross-check;
seal truth + manifest + public package.

Data flow (run): POLICY ⇄JSONL⇄ HARNESS ⇄JSONL⇄ ENV → trajectory →
SCORER(findings + trajectory + sealed truth) → reward + receipt.

Never public: `truth.json`, `provenance.json`, mutation params, clean
twin (if revealing), private seeds, ProofGraph, hidden labels, salt
before reveal, live scorer config. Public manifest must not contain
finding counts/types, affected IDs, operator names, clean flags.

## Anomaly types (provisional taxonomy, A-002)

`DUPLICATE_PAYMENT`, `PARTIAL_PAYMENT_ALLOCATION`, `FX_RATE_MISMATCH`,
`PERIOD_CUTOFF`. Affected-ID rules in `spec/anomaly_catalog.yaml`
(provisional). Invariants INV-01…INV-17 in `spec/invariants.yaml`.

## Reward (provisional, A-005)

`R = max(0, F1 − ETA·steps_used/max_steps)`, ETA=0.05, max_steps=100.
Match requires type + exact canonical affected IDs + currency +
|amount diff| ≤ tolerance + one full evidence set. Deterministic maximum
matching with lexicographic tie-break. See Master TZ 15.

## Determinism / money / time

- Namespaced RNG from SHA-256(namespace + master seed); global `random`
  forbidden (REQ-GEN-001…006).
- Money: integer minor units; Decimal from strings; exponents in
  `contracts/currency.json` (KZT/USD/EUR=2, JPY=0, KWD=3).
- Time: ISO-8601 with offset; period in company timezone; zoneinfo.

## Test strategy / release blockers

Unit + contract + property/metamorphic + differential/mutation +
security/replay/acceptance. Any of: truth/seed leak, policy→scorer
access, real data, broken reset/step, unverified truth, exploitable
reward, replay mismatch, silently skipped required check, false
README/CLI, untested submission package — blocks release (TZ 29.6).

## Repository map

See `docs/CONTEXT/ARCHITECTURE_SNAPSHOT.md` and Master TZ 6.
Phase 1: skeleton, contracts frozen v1.0.0, canonical JSON,
models, boundary scan, CI, docs. Phase 2 adds core primitives and grouped checks (see PHASE_REPORTS/PHASE-02.md).

## Source-of-truth files

`contracts/` (schemas), `contracts/version.json`, `spec/`,
`configs/`, `judge/rubric_map.json`, `docs/DECISIONS.md`,
`docs/CURRENT_STATE.md`, `docs/STATUS.md`.
