# TwinLedger — Decision Log (append-only)

Format: `D-<phase>-<nn>` + date + status. Never rewrite history; add a
new entry to supersede.

## D-00-01 (2026-11-20) — Official organiser contract status: UNKNOWN

The attached Master TZ v3.0.0 is preserved verbatim at
`docs/reference/TwinLedger_v3_Master_TZ_AI_Agents.txt` (SHA-256
`a46cdb63bb4b41aabb95a842406f5a4fff91e218ead1e4f97b22b60d1c748e36`).
No separate organizer-issued TZ, rubric, sample I/O or starter code was
present in the repository at Phase 0/1 start (repo contained only
`README.md` + initial commit `c961a00`). All Master TZ assumptions
A-001…A-016 about the competition are therefore **UNRESOLVED** and
isolated in `adapter/` + `configs/`. Owner: A0. Closure condition:
organizer contract published → copy to `docs/official/`, record
hash/date/source, update this log + `docs/QUESTIONS.md`.

## D-01-01 (2026-11-20) — Contract freeze v1.0.0 for MVP (Phase 1)

Schemas in `contracts/` frozen at `1.0.0` (`contracts/version.json`).
Further changes require an approved CR (`docs/CR/`). Owner: A0.
Rationale: TZ Phase 1 exit gate.

## D-01-02 (2026-11-20) — Flat package layout (no `twinledger/` prefix)

Top-level packages `gen/`, `verifier/`, `env/`, … per Master TZ 6, so
import-boundary rules map 1:1 to directories. Owner: A0.

## D-01-03 (2026-11-20) — Stdlib-only core; optional extras isolated

Core uses Python 3.11 stdlib only (`requirements-core.txt` empty).
`pytest`/`hypothesis`/`jsonschema` are dev-only; `gymnasium`/`numpy`/
`scikit-learn`/`matplotlib` are extras. Owner: A0. (TZ 22.1–22.2)

## D-01-04 (2026-11-20) — Sealed data git policy (provisional)

`episodes/*/sealed/` and `episodes/hidden/` are git-ignored by default
(`.gitignore`). Public episode fixtures may be committed. Revisit in
Phase 0 once organiser submission rules are known. Owner: A0.

## D-01-05 (2026-11-20) — Provisional reward/budget in configs, not code

`configs/scoring/default.json` (ETA=0.05, max_steps=100) and
`configs/environment/default.json` (CLOSED_EVAL, 100 steps, page 50)
hold provisional values (A-004/A-005). Code must read them; no hidden
defaults. Owner: A0.

## D-01-06 (2026-11-20) — Rubric map is provisional

`judge/rubric_map.json` has `provisional: true`. Internal test counts
must never be presented as official organiser checks (TZ 23.4/23.6).
Owner: A0/D.

## Assumptions register (A-001…A-016)

All UNRESOLVED pending D-00-01 closure. Isolated in `adapter/` +
`configs/`; not baked into core logic. See `docs/QUESTIONS.md` Q-001…Q-014.

## D-02-01 — local primitive conventions (provisional)
FX rate input is positive fixed-point text in target/source direction. Conversion
accepts signed int64 inputs/outputs and records one final rounding operation.
Monthly and quarterly periods use month-aligned fiscal calendars; quarters are
labelled by fiscal start year. Reject gaps; reject folds unless explicitly resolved.
A date without time is a company business date, not a machine-local instant.
Aging labels and open/partial/paid statuses are MVP group semantics, not organizer rules.

## D-06-00 (2026-11-21) — Phase 6 base line: frozen-contract stack of PR #1/#2

Phase 6 (matcher + base reward) is implemented on top of the Phase 1 +
Phase 2 stack (branch `arena/2a69516d-...`, commits ae5650e..ef15218,
fast-forwarded into the session branch), which carries the first
contract freeze v1.0.0 (D-01-01). Parallel session branches (`arena/
6e3d45bc-...` Phase 0/1 alternative, `arena/280879b6-...` Phase 3,
`arena/d94e8b76-...` Phase 4, `arena/eb1e0f8a-...` Phase 5) claim
incompatible v1.0.0 schema sets (see CR-05-01 follow-up and issue #3).
Per the priority rules, the earliest frozen contract (D-01-01) wins
until A0 issues an approved CR; Phase 6 consumes domain models only and
does not touch any disputed wire format. Owner: A0. Closure: issue #3
disposition + merged contract line. Draft CR: `docs/CR/CR-06-01.md`.

## D-06-01 (2026-11-21) — Finding/truth schemas adopted as scoring boundary

Task 6.1: `contracts/finding.schema.json` v1.0.0 (schema_version,
type, typed affected_ids, claimed_amount int minor units, currency,
evidence_ids) and `contracts/truth.schema.json` v1.0.0 (amount_minor,
tolerance_minor, evidence_sets) are confirmed as the scoring input
boundary. No schema file was modified. Status: PROVISIONAL pending the
official organiser contract (Q-003). Scoring validates every input at
its module boundary (REQ-CONTRACT-002) and re-validates canonicalised
round-trips.

## D-06-02 (2026-11-21) — Empty-denominator conventions for precision/recall/F1

TZ 15.4 requires explicitly established special rules. Conventions
(kept in `scoring/reward.py`, all executable in tests): clean book +
empty submission => F1 = 1; precision = 1 for an empty submission;
recall = 1 for an empty truth; otherwise F1 = 2TP/(2TP+FP+FN). These
match every sanity example A-J of TZ 15.6. PROVISIONAL until the
official rubric is published (Q-005).

## D-06-03 (2026-11-21) — Exact rational reward, display-only decimals

Reward, F1, precision, recall and penalty are computed as exact
`fractions.Fraction` values; eta is parsed from the config literal text
(Decimal-from-string, never binary float). Decimal strings are
rendered only for display (ROUND_HALF_EVEN, 7 places); raw values are
stored exactly (TZ 15.5). `steps_used` must satisfy
0 <= steps_used <= max_steps (bounded error otherwise).

## D-06-04 (2026-11-21) — Formalised tie-break of the matcher

Among all matchings with maximum cardinality and minimum total absolute
amount error, `scoring/matcher.py` selects the lexicographically
smallest sorted pair tuple ``(finding_index, truth_index)``. Implemented
as greedy pair locking with exact min-cost-flow feasibility checks on
top of a min-cost max-flow solve; the original input index is used only
as this final tie-break (REQ-SCORE-002). Bounded error above 4096
candidate edges instead of a silent determinism downgrade.

## D-06-05 (2026-11-21) — Match predicate scope and experimental column

The match predicate is exactly the six conditions of TZ 15.2
(PROVISIONAL pending Q-005); explanation/confidence never influence
matching or reward. `experimental_grounded_score` (TZ 15.8) is computed
only from caller-supplied requested evidence IDs, is labelled
EXPERIMENTAL and lives in a separate diagnostics column that never
feeds the reward. Explanation-consistency (Phase 10) and verifier
quality (Phase 8) diagnostics are explicit NOT_AVAILABLE markers.

## D-07-01 — Provisional normalized operator boundary

Implement FX and cutoff against normalized journal inputs without introducing
an episode schema or affected-ID translation. For FX select the latest allowed
quote date only under the declared fallback policy; reject distinct permitted
booked amounts rather than guessing a source-priority rule. Keep official
semantics open under Q-004/Q-006; integrate only after A0 resolves CR-06-01.

## D-08-01 (2026-11-21) — Zero common-mode verifier implementation

`verifier/` imports only Python 3.11 stdlib and `contracts/` (schemas,
canonical JSON, ISO-4217 currency exponents). It deliberately does **not**
import `core/`, `invariants/`, `gen/`, or `scoring/`. FX conversion is
independently implemented in `verifier/money_time.py` using exact
`fractions.Fraction` intermediate arithmetic with a single final rounding step
(`half_even`/`half_up`) and inverse-pair support; company-local date and fiscal
period mapping is independently implemented via `zoneinfo.ZoneInfo`. This
eliminates common-mode helper bugs between generator/invariants and the
independent verifier (TZ §12.4, §13.1).

## D-08-02 (2026-11-21) — Stage-1/Stage-2 crosscheck separation & digest lock

To satisfy REQ-ORG-003, REQ-ARC-001, and REQ-VER-020..022 without letting
`verifier/` see sealed truth or letting `scoring/` import `verifier/`, Stage-1
discovery (`verifier.discover`) outputs a schema-valid `verifier_report` and
pre-committed SHA-256 `report_digest` from `public/` alone, while Stage-2
crosscheck (`scoring/crosscheck.py`) consumes the serialized `verifier_report`
dict, verifies `expected_report_digest`, delegates TP/FP/FN to
`scoring.matcher.optimal_matching` with strict per-set (non-union) evidence
sufficiency checks, and sets `release_blocked=True` on any mismatch,
ambiguity, insufficiency, or ablation failure. `scoring/diagnostics.py` retains
its explicit `verifier_quality: NOT_AVAILABLE` marker for agent scoring until
episode pipeline integration.

## D-08-03 (2026-11-21) — Frozen independent verifier spec & provisional semantics

`spec/verifier_algorithm.md` (v1.0.0) freezes the independent verifier
algorithm, ProofGraph DAG contract, minimal-evidence ablation protocol, and
16-distractor exclusion rules without reading `gen/` (Task 8.1). Provisional
public-episode `affected_ids` and amount conventions follow
`spec/anomaly_catalog.yaml` and `docs/DATA_DICTIONARY.md` (pending external
organiser clarifications `Q-004/Q-006`).

## D-08-04 (2026-11-21) — Resolution of CR-06-01 & Phases 3–5/7–8 full integration

Resolved `docs/CR/CR-06-01.md` on the frozen Phase 1 v1.0.0 contract line
(`D-01-01`, zero frozen schema edits):
- Integrated deterministic Clean Twin generator (`gen/core/clean_twin.py`,
  `gen/core/rng.py`, `gen/distractors/catalog.py`) and all 4 anomaly operators
  + structural diff + salted truth commitment + manifest serializer
  (`gen/errors/operators.py`, `gen/truth.py`, `gen/serialize.py`,
  `gen/pipeline.py`), reusing Phase 7's `gen/errors/fx_cutoff.py`.
- Integrated frozen-contract-compliant public-only `env/` (`list_records`,
  `get_record`, `get_document`, safe AST `calc`, `submit`, opaque HMAC cursors,
  `CLOSED_EVAL`, JSONL stdio server) and provisional `adapter/organizer.py`.
- Added `episodes/*/*/sealed/` to `.gitignore` so sealed truth/provenance
  directories under `episodes/dev/<ep_id>/` and `episodes/train/<ep_id>/` are
  never committed to Git while remaining deterministically regenerable via
  `tools/make_dataset.py --split all`.
- Generated 10 episodes (6 `dev` + 4 `train`) and verified 100% (10/10) through
  manifest SHA-256 checks, Stage-1 public-only `verifier.discover`, Stage-2
  `scoring.crosscheck` (`release_blocked=False`), and `TwinLedgerEnv` public
  tool reachability — promoting EXIT GATE 8 to **DONE** (internal provisional
  contract line; external organiser items `Q-003..Q-006` and `make docker-check`
  remain explicitly documented).
