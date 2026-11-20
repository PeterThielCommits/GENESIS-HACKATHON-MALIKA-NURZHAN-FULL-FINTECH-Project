# TwinLedger

**A proof-carrying, deterministic audit environment for AI accounting agents.**
*Trust, but verify the verifier.*

TwinLedger generates fictional companies with invoices, payments, bank lines, journal
entries, FX rates and an accounting policy. Some books are clean; others contain a controlled
accounting anomaly. An agent explores only the public records through a small set of read-only
tools and submits structured findings, which are scored against a sealed reference produced by
a **counterfactual twin** and independently confirmed by a **separate verifier**.

> **Current status: Phase 0 and Phase 1 complete (foundation and contract freeze).**
> The environment, generator, verifier and scorer are **not implemented yet** — the Make
> targets that would run them exit `5` and say so. What exists is a frozen, hashed contract set,
> typed models that provably mirror it, the isolation boundary, the governance records, CI that
> runs the same gate as your laptop, and the verification harness that keeps all of it honest.
> See `docs/STATUS.md` for the gate table, `docs/PHASE_REPORTS/PHASE-00.md` and
> `PHASE-01.md` for executed commands and real results, and `docs/PHASE0_CHECKLIST.md` for the
> specification's Phase 0 tasks one by one.

## What is official and what is not

* **No organizer contract is archived in this repository.** No official specification,
  rubric, starter code or sample I/O was available (`docs/official/MANIFEST.json`,
  `docs/official/SOURCE_SEARCH_LOG.md`).
* Therefore the whole external surface is **provisional** and isolated behind `adapter/` and
  `configs/`. `adapter/` currently **fails closed**: the profile is `UNBOUND`, so an official
  run is impossible by design rather than by accident.
* The reward formula (`max(0, F1 - 0.05·steps/100)`) and the 25/25/25/15/10 rubric split are
  our *provisional reading* of the master specification. No report here claims an official
  score, and internal checks are never called official checks.

## Quick start

Requires **Python 3.11** (3.11.x). Nothing is installed and no network access is used.

```bash
make setup          # verify the interpreter and list optional extras
make lint           # compile, import boundaries, contract + registry freshness
make test           # unit, contract and Phase 0 tests (stdlib unittest)
make verify-core    # the Phase 0 gate: checks + artifacts + exit code
make verify         # same runner, full profile (planned checks reported BLOCKED)
make golden         # the contract set still matches its recorded freeze
make models         # typed models still mirror the schemas (parity + round-trip)
make probe          # look for official starter code; skips honestly when absent
make help           # every command with a one-line description
```

Exit codes follow the master specification §23.3: `0` all required checks pass, `1` a
required check failed, `2` configuration/contract error, `3` resource/environment error,
`4` release blocker (leak or false official claim), `5` suite incomplete / not implemented.

## Architecture in one screen

```
build:   seed ─► RNG streams ─► CLEAN BOOK C ─► invariants
                                   │
                    operators O1..On ─► MUTATED BOOK M
                                   │
              canonical diff(C,M) ─► candidate truth ─┐
                                   │                  │
                     independent verifier (public) ◄──┘
                                   │
                    crosscheck ─► sealed/truth.json + commitment

run:     POLICY ◄─JSONL─► HARNESS ◄─JSONL─► ENV (public/ only)
                             │
                        trajectory hash chain
                             │
                    env closed ─► SCORER(sealed truth) ─► reward + receipt
```

Details: `docs/DESIGN.md` (intent), `docs/CONTEXT/ARCHITECTURE_SNAPSHOT.md` (what exists
today), `docs/THREAT_MODEL.md` (assets, boundaries, controls — including what is *not*
enforced), `docs/LIMITATIONS.md` (what is not guaranteed).

## Repository map

| Path | Contents |
|------|----------|
| `contracts/` | Public schemas, fixtures, versioning, currency registry, `CONTRACT.md` |
| `adapter/` | The only place that knows external organizer names (currently unbound) |
| `configs/` | Every provisional number, limit and formula (versioned, hashed into manifests) |
| `spec/` | Anomaly catalog (4 types, 16 distractors) and invariant catalog (17 invariants) |
| `tools/` | Canonical JSON, schema validator, governance/boundary scans, verify runner |
| `judge/` | Internal rubric map (provisional, never official) |
| `tests/` | Contract, unit and Phase 0 governance tests |
| `docs/` | Context, decisions, questions, risks, reports, phase evidence |

## Input/output examples

Finding (schema `contracts/finding.schema.json`):

```json
{
  "schema_version": "1.0.0",
  "type": "DUPLICATE_PAYMENT",
  "affected_ids": ["JE:JE-000123", "PAY:PAY-7F3A91"],
  "claimed_amount": 18450000,
  "currency": "KZT",
  "evidence_ids": ["INV:INV-2025-0042", "JE:JE-000123", "PAY:PAY-4C21B0", "PAY:PAY-7F3A91"],
  "explanation": "Invoice INV-2025-0042 was settled twice by two distinct bank transfers.",
  "confidence": 0.82
}
```

Tool response (schema `contracts/tool_response.schema.json`):

```json
{"schema_version": "1.0.0", "protocol_version": "1.0.0", "request_id": "req-0001",
 "ok": true, "result": {"rows": [], "next_cursor": null},
 "info": {"steps_used": 1, "steps_remaining": 99}}
```

These are contract fixtures, not an implemented server.

## Resource limits (provisional)

Python 3.11, offline, ~2 CPU / 4 GB RAM / 1 GB disk, `make verify` < 10 minutes,
env step p99 < 5 ms, L4 episode < 50 MB — targets from the master specification, to be
measured and reported with host details (`configs/environment/resources.json`).

## Known limitations (short version)

No organizer contract; no OS-level sandbox; no runtime yet; four anomaly types only;
statistical shortcut tests are evidence, not proof; licences not yet reviewed.
Full list, with reasons: **`docs/LIMITATIONS.md`**.

## Documentation index

`AGENTS.md` (agent rules) · `docs/PROJECT_CONTEXT.md` (mission, architecture) ·
`docs/CURRENT_STATE.md` (branch, phase, next action) · `docs/STATUS.md` (gate table) ·
`docs/DECISIONS.md` (D-0001…D-0020) · `docs/QUESTIONS.md` (Q-001…Q-014) ·
`docs/ASSUMPTIONS.json` (A-001…A-016) · `docs/REQUIREMENTS.json` (186 requirements) ·
`docs/RUBRIC_TRACEABILITY.md` · `docs/RISK_REGISTER.md` · `docs/THREAT_MODEL.md` ·
`docs/INDEPENDENCE.md` · `docs/DATA_DICTIONARY.md` · `docs/GIT_AND_DATA_POLICY.md` ·
`docs/PHASE_REPORTS/PHASE-00.md`.
