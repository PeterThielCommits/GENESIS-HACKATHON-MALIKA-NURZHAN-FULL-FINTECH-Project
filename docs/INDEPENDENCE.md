# TwinLedger — Verifier Independence

## Ownership

- Generator (Zone 1): Owner A.
- Verifier (Zone 3): Owner C (different human owner, REQ-ORG-001).
- Verifier receives `contracts/`, `spec/`, and public episode data only — never
  `gen/`, provenance, mutation parameters, or truth during discovery
  (REQ-ORG-002, REQ-VER-001, REQ-VER-002).
- Phase 8 specification (`spec/verifier_algorithm.md`, v1.0.0) and
  implementation (`verifier/`) were authored strictly from frozen contracts
  (`contracts/`), normative specifications (`spec/`), and Master TZ v3.0.0
  Section 13 **without reading `gen/`** (Task 8.1).

## Two-stage discovery / crosscheck architecture (REQ-ORG-003, REQ-VER-020..022)

1. **Stage 1 (`verifier.discover`)** operates solely on `public/` (either a
   `PublicEpisode` or path to a `public/` directory). It runs independent
   discovery across all four anomaly types, constructs a deterministic
   `ProofGraph` DAG, runs minimal-evidence ablation and public-tool
   reachability checks, validates the resulting `verifier_report.json` against
   `contracts/verifier_report.schema.json`, and commits to a canonical SHA-256
   `report_digest` before any truth data can be seen.
2. **Stage 2 (`scoring.crosscheck.crosscheck`)** runs strictly *after* Stage 1
   in Zone 2 (`scoring/`). It verifies the pre-committed `report_digest`
   (rejecting any post-hoc tampering), validates the report against the frozen
   schema, matches verifier findings against sealed `TruthFinding` records via
   `scoring.matcher.optimal_matching` without cross-set evidence unions,
   computes all TZ §13.7 exact `Fraction` metrics, and blocks release
   (`release_blocked=True`) on any FP, FN, unresolved ambiguity, evidence
   insufficiency, or ablation failure.

## Implementation boundaries (Phase 8 status)

- `verifier/` imports **ONLY** Python 3.11 standard library and `contracts/`
  (frozen schemas, canonical JSON, currency exponents).
- `verifier/` does **NOT** import `gen/`, `core/`, `invariants/`, `scoring/`,
  `env/`, `harness/`, `seal/`, or `arena/`.
- `verifier/` contains **zero** string literals referring to private paths
  (enforced statically by `tools/check_import_boundaries.py`, REQ-ARC-001..007).
- `verifier/public_loader.py` enforces an explicit 12-file public allowlist,
  rejects dotfiles, `index_hints.json`, unexpected extra files, and symlinks
  escaping `public/`.
- `scoring/crosscheck.py` does **NOT** import `verifier/` or `gen/` — it
  consumes only the serialized `verifier_report` JSON artifact and sealed
  `TruthFinding` objects.

## Shared dependencies & common-mode failure disclosure (TZ §12.4)

| Module / dependency | Shared with generator? | Rationale & common-mode mitigation |
|---|---|---|
| `contracts/` (`canonical.py`, `validate.py`, `currency.py`, `*.schema.json`) | Yes (allowed per TZ §3) | Shared frozen wire contracts, canonical SHA-256 hashing, and ISO-4217 exponent table only — contains zero detection, FX-rounding, or accounting logic. |
| `core/money.py`, `core/time_rules.py`, `core/ids.py` | **No** | Eliminated common-mode risk: `verifier/money_time.py` independently implements exact `fractions.Fraction` intermediate FX conversion (supporting direct and inverse ISO pairs) and `zoneinfo.ZoneInfo`-based fiscal period resolution. |
| `invariants/checks.py` | **No** | Eliminated common-mode risk: `verifier/` implements independent rule-driven detectors (`duplicate_payment.py`, `partial_allocation.py`, `fx_mismatch.py`, `period_cutoff.py`) with ProofGraph derivation and explicit distractor exclusion edges. |
| `gen/` | **No** | Zero imports, zero shared helpers, never read during Phase 8 spec/implementation (Task 8.1). |

## Verification evidence (Phase 8)

- `make lint` → `import boundary scan: CLEAN (REQ-ARC-001..007)`.
- `tests/unit/test_import_boundaries.py` → PASS (static AST + literal scan).
- `tests/verifier/test_boundaries.py` → 5 tests PASS:
  - repo boundary scanner clean;
  - AST scan across all `verifier/*.py` confirms zero imports of `gen`, `core`, `invariants`, `scoring`, `env`, `harness`, `seal`, `arena`;
  - fresh Python subprocess importing `verifier` loads none of those packages;
  - runtime `io.open`/`Path.open` spy on an episode directory containing sibling `sealed/` (`truth.json`, `provenance.json`) and `manifest.json` proves every single file open stays strictly inside `public/`;
  - negative tests prove dotfiles, `index_hints.json`, extra non-allowlisted files, and escaping symlinks are rejected with `PublicEpisodeError`.
