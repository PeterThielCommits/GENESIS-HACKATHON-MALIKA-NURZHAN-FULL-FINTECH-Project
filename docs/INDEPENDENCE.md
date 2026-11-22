# TwinLedger — Verifier Independence

## Ownership — and an honest correction

**This is the weakest link in the independence claim, so it is stated first.**

Master TZ §4 requires that the independent verifier be built under a *different
human owner or agent context* from the generator (REQ-ORG-001, REQ-ORG-002).
The zone model names four owners and `.github/CODEOWNERS` maps the directories
to them:

- Generator (Zone 1): Owner A.
- Verifier (Zone 3): Owner C.
- Verifier receives `contracts/`, `spec/`, and public episode data only — never
  `gen/`, provenance, mutation parameters, or truth during discovery
  (REQ-ORG-002, REQ-VER-001, REQ-VER-002).

**What is actually true as of v1.0.0:** this repository was produced by AI agents
working in one shared session context, not by four separate human owners. The
*organisational* half of REQ-ORG-001 (two humans, two contexts) therefore **is
not evidenced** and must not be claimed. The *technical* half **is** evidenced,
mechanically and continuously, and it is the half that determines whether a
generator bug can silently become a verifier assumption:

| Independence property | How it is proven | Evidence |
|---|---|---|
| `verifier/` cannot import `gen/`, `core/`, `invariants/`, `scoring/`, `env/`, `harness/`, `seal/`, `arena/`, `nlp/` | AST scan over every file, plus a fresh-subprocess import test | `tools/check_import_boundaries.py` (RC-002, release blocker), `tests/verifier/test_boundaries.py` |
| `verifier/` never reads a sealed file at runtime | `io.open`/`Path.open` spy over an episode that *has* sibling `sealed/truth.json` | `tests/verifier/test_boundaries.py` |
| Verifier does not share detection logic with the generator | independent `verifier/money_time.py` (`Fraction` FX, `zoneinfo` periods) and independent detectors; no import of `core/money.py` or `invariants/checks.py` | `docs/INDEPENDENCE.md` §"Shared dependencies" |
| Stage-1 output is committed before truth is visible | canonical SHA-256 `report_digest` committed first, verified by Stage 2, which rejects post-hoc tampering | `scoring/crosscheck.py`, `tests/verifier/` |
| Independence holds under ablation, not just inspection | every truth finding must survive evidence deletion and be reachable through public tools | `verifier/minimal_sets.py`, `EXIT GATE 8` |

So the correct statement is: **zero-common-mode independence is enforced and
tested between the generator and the verifier as software; it is not evidenced
as an organisational separation of different people.** A judge should treat the
former as a property they can verify themselves by running `make lint` and
`tests/verifier/test_boundaries.py`, and the latter as an unmet process
requirement recorded in `docs/QUESTIONS.md`.
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

## Re-derivation evidence (2026-11-22, second from-scratch implementation)

The handoff in `docs/CONTEXT/NEXT_AGENT.md` scoped a fresh verifier authored from
`spec/` and `contracts/` alone as the technical remedy short of organisational
separation. That re-derivation now exists and is continuously tested:

- **`independent_verifier/`** — a second, from-scratch Stage-1 implementation
  (own money/FX primitives via `Fraction` + `zoneinfo`, own discovery algorithms
  written from `spec/verifier_algorithm.md`, own ProofGraph DAG with acyclicity
  and finding-path checks, own evidence minimality/ablation). It imports **only**
  the standard library and the frozen `contracts/` package — never `verifier/`,
  `gen/`, `scoring/`, `env/`, `harness/`, `seal/`, `nlp/`, `arena/` or `judge/`
  (enforced by `tools/check_import_boundaries.py` and by
  `tests/independent_verifier/test_independent_rederivation.py`).
- **Agreement on every committed episode:** all 6 `episodes/dev/*` and 4
  `episodes/train/*` on-disk episodes re-derive to the exact same findings
  (type, affected_ids, claimed_amount_minor, currency) with identical
  `episode_public_hash` values.
- **Agreement on the official matrix:** the 20 official `D01..D20` scenarios,
  rebuilt from the public recipe matrix (`master_seed=2026`), are re-derived and
  cross-checked against sealed truth: **F1 = 1 (exact), FP = 0, FN = 0
  everywhere**, evidence enumeration complete, no ProofGraph invariant errors.
- **Machine-readable evidence:** `docs/EVIDENCE/independent-rederivation-2026-11-22.json`
  (produced by `tools/verify_independent_rederivation.py`); regression-locked by
  `tests/independent_verifier/test_independent_rederivation.py` (8 tests,
  including a runtime file-open spy proving discovery never leaves `public/`,
  a fresh-subprocess import test, and zero-common-mode AST scans).
- **What this does NOT prove:** organisational separation. Both implementations
  were authored in a single AI-agent-assisted session by the same operator.
  Agreement between them is strong *technical* evidence against common-mode
  detection defects (a shared wrong assumption would almost never survive two
  independent codebases written from the same spec); it is **not** evidence
  that a different human or agent context built the verifier.
  `Q-ORG-01` therefore remains **OPEN** on purpose.
