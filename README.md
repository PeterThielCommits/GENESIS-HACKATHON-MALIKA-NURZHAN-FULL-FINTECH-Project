# TwinLedger

Proof-carrying audit environment for AI agents — a deterministic,
synthetic-accounting benchmark with counterfactual twins, an independent
verifier, sealed evaluation and reproducible receipts.

> TwinLedger is a research/competition environment. It is **not** a real
> accounting system, audit service, tax/legal advisor or company
> certification tool. All companies, banks, counterparties, documents and
> operations are fictional and generated programmatically.

## Quick start (offline, Python 3.11, stdlib only)

```bash
make setup        # check Python 3.11 + optional extras (no downloads)
make lint         # compile check + import-boundary scan
make test         # unit + contract tests
make verify-core  # critical core + release blockers
make verify       # full rubricator + reports
```

Artifacts: `artifacts/reports/latest/verify_summary.json` (+ `.txt`).

## Official compatibility status

The official organiser contract has **not** been published in this
repository yet. All tool names, reward parameters and ID rules below are
**provisional** (Master TZ assumptions A-001…A-016) and isolated in
`adapter/` + `configs/`. See `docs/DECISIONS.md` and `docs/QUESTIONS.md`.

## Architecture overview

```
clean twin C ──operators──▶ mutated twin M
     │ diff(C,M) → candidate truth          (gen/, Zone 1)
     ▼
verifier reads ONLY public M → independent findings + ProofGraph (verifier/, Zone 3)
     ▼
env exposes public tools (reset/step)      (env/, Zone 2)
policy ──JSONL──▶ harness ──JSONL──▶ env
episode ends → scorer (sealed truth) → reward + receipt + replay (scoring/, seal/, Zone 2)
judge kit: one command, machine-readable reports (judge/, Zone 4)
```

Environment never loads truth/provenance/sealed (REQ-PROD-005). Policy
never imports scorer/verifier/generator internals (REQ-ARC-003).

## Core commands

| Command | Purpose |
|---|---|
| `make help` | list targets |
| `make setup` | Python/extras check |
| `make lint` | compile + boundary scan |
| `make test` | unit + contract tests |
| `make test-property` | property tests (stdlib fallback) |
| `make build-episodes` | generate episodes (Phase 3+) |
| `make verify-core` / `make verify` | verification gates |
| `make replay` / `make audit-shortcuts` / `make mutation-test` | later phases |
| `make report` | aggregated report |
| `make docker-check` | offline Docker smoke |
| `make clean` | remove generated artifacts |

## Input/output examples

Valid finding (`contracts/finding.schema.json`):

```json
{
  "schema_version": "1.0.0",
  "type": "FX_RATE_MISMATCH",
  "affected_ids": ["JE:je_demo_001"],
  "claimed_amount": 1250,
  "currency": "KZT",
  "evidence_ids": ["JE:je_demo_001", "FX:fx_demo_17", "INV:inv_demo_9"]
}
```

Tool request (`contracts/tool_request.schema.json`):

```json
{
  "protocol_version": "1.0",
  "request_id": "req-0001",
  "action": {"tool": "list_records", "args": {"table": "payments", "cursor": null, "limit": 25, "filters": {}}}
}
```

## Resource limits (provisional, TZ 22.5)

2 CPU / 4 GB RAM / 1 GB disk, offline, Python 3.11. Core targets:
env step p99 < 5 ms, one L4 episode < 50 MB, peak < 300 MB,
`make verify` < 10 min on the target host (to be measured, not claimed).

## Current known limitations

- Phase 1 only: contracts, canonical JSON, models, boundary scan, CI,
  docs. Generator, env, scoring, verifier, harness are **not yet
  implemented** (see `docs/CURRENT_STATE.md`).
- Official organiser contract/rubric unknown — everything provisional.
- Process separation is planned, not yet implemented; no sandbox claims.

See `docs/LIMITATIONS.md`, `docs/DESIGN.md`, `docs/PROJECT_CONTEXT.md`.

## Phase 2: accounting primitives

Run `make setup verify-core` with Python 3.11. See the [Phase 2 report](docs/PHASE_REPORTS/PHASE-02.md)
for the implemented boundaries and the [manual accounting vectors](tests/fixtures/manual/).
