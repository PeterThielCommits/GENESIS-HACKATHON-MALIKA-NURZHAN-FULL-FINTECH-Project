# TwinLedger — Design (Phase 1)

## Decisions

- Flat packages per Master TZ 6 (D-01-02). Import rules are directory
  rules, machine-checked by `tools/check_import_boundaries.py`.
- Contracts are the frozen boundary (D-01-01). Schemas are JSON Schema
  draft-07; core validation is stdlib-only (`contracts/validate.py`)
  so offline runs never need `jsonschema`.
- Canonical JSON is the single hashing primitive (TZ 7.2):
  UTF-8, `ensure_ascii=False`, sorted keys, `(",", ":")`, no NaN/Inf,
  LF-terminated bytes, money as int, Decimal as pre-formatted string.
- Configs are versioned envelopes; `config_hash` = SHA-256 of canonical
  JSON (REQ-CONTRACT-021). Unknown config versions are bounded errors.
- Unknown public fields are rejected; extensions must be namespaced
  `x_twinledger_*` (REQ-CONTRACT-003).

## Process boundaries (planned, Phase 9)

P0 harness (supervisor) · P1 policy (external client, JSONL only) ·
P2 env (public/ read-only) · P3 scorer (after env closes, sealed truth).
Process separation alone is **not** a sandbox; platform controls are
recorded per `security_profile` in Phase 9. No sandbox claims in Phase 1.

## Truth lifecycle (planned, Phases 3–4/8)

Clean C → operators → M → diff(C,M) → candidate truth → independent
verifier on public M → cross-check → commit-reveal seal → manifest.
Diff proves *what changed*, not *that it is an error*; invariants +
verifier prove semantic wrongness.

## Scoring design (planned, Phase 6)

Canonical typed IDs (`JE:`, `INV:`, …), exact match predicate
(type + IDs + currency + amount ≤ tolerance + full evidence set),
deterministic maximum matching with lexicographic tie-break, F1 +
provisional step penalty from `configs/scoring/default.json`.

## Key data flows

Build: `gen` → `verifier` (public only) → `seal` → `episodes/`.
Run: `policy` ⇄ `harness` ⇄ `env` → trajectory → `scoring` → receipt.
Verify: `judge/verify.py` → `artifacts/reports/latest/`.

## Module map

See `docs/CONTEXT/ARCHITECTURE_SNAPSHOT.md`.
