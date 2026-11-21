# Phase 6 — MATCHER И БАЗОВАЯ НАГРАДА

## Outcome

DONE (with the official-formula caveat below)

## Objectives

Make reward precise, transparent and independent of wording (Master TZ
v3.0.0, section 24, Phase 6): freeze the finding canonical schema,
canonicalise IDs and validate findings, implement the match predicate,
deterministic maximum matching with formalised tie-break, TP/FP/FN +
F1 + reward, the five mandatory reward-property suites and a
brute-force differential matcher.

Official-rubric caveat (EXIT GATE 6 wording): the matcher and reward
are stable and deterministic and conform to the Master TZ specification;
the reward formula, tolerance semantics and match criteria are marked
**provisional** because the official organiser rubric is not published
(assumptions A-005/A-006, questions Q-003/Q-005 — EXIT GATE 6 explicitly
allows "clearly marked provisional if rubric not published").

## Requirements

| REQ ID | Status | Where |
|---|---|---|
| REQ-SCORE-001 (TP/FP/FN only in matcher) | CONFIRMED (provisional rubric) | `scoring/matcher.py::optimal_matching` |
| REQ-SCORE-002 (deterministic, permutation-invariant; index = last tie-break) | CONFIRMED | `scoring/matcher.py::optimal_pairs`, `tests/scoring/test_matching_order.py` |
| REQ-SCORE-003 (no truth matched twice) | CONFIRMED | flow capacities + tests |
| REQ-SCORE-004 (duplicates/split/extra cannot inflate TP) | CONFIRMED | `tests/scoring/test_reward_sanity.py` C/I, property P3 |
| REQ-SCORE-005 (same pair -> same match) | CONFIRMED | `match_predicate` pure, tested |
| REQ-CONTRACT-002 (input validation at boundary) | CONFIRMED | `scoring/canon.py`, tests |
| REQ-CONTRACT-021 (config hash) | CONFIRMED | `scoring/reward.py::load_scoring_config` |
| TZ 15.1 canonicalisation | CONFIRMED | `scoring/canon.py` |
| TZ 15.2 six match conditions | PROVISIONAL (Q-005) | `scoring/matcher.py::match_predicate` |
| TZ 15.3 max matching + tie-break + exhaustive cross-check | CONFIRMED | `scoring/matcher.py`, `scoring/exhaustive.py` |
| TZ 15.4-15.5 F1 rules + exact reward | PROVISIONAL (A-005/Q-005) | `scoring/reward.py` |
| TZ 15.6 sanity examples A-J | CONFIRMED (all executable) | `tests/scoring/test_reward_sanity.py` |
| TZ 15.7 five reward properties | CONFIRMED | `tests/scoring/test_reward_properties.py`, matrix artifact |
| TZ 15.8 experimental grounded score | CONFIRMED (separate column) | `scoring/diagnostics.py` |
| TZ 15.9 diagnostics | CONFIRMED (Phase 8/10 items = NOT_AVAILABLE) | `scoring/diagnostics.py` |
| REQ-PROD-025 (differential matcher tests) | CONFIRMED | `tests/scoring/test_differential.py` |
| REQ-TEST-003 (seeds recorded) | CONFIRMED | differential tests use fixed seeds 0..59 / 1000..1039 / 5000..5009 |

## Implementation summary

- `scoring/canon.py` — typed-ID canonicalisation (NFC, namespace check,
  sort, dedupe; prefixes kept), strict finding/truth boundary validation
  with indexed bounded errors.
- `scoring/matcher.py` — six-condition match predicate (explanation and
  confidence ignored); candidate-edge matrix; exact three-level matching
  (max pairs -> min total |Δamount| -> lexicographically smallest sorted
  pair tuple) via min-cost max-flow + greedy pair locking with exact
  feasibility checks; MatchResult is the single source of TP/FP/FN.
- `scoring/reward.py` — precision/recall/F1 with documented
  empty-denominator rules; `R = max(0, F1 - eta*steps/max_steps)` in
  exact rational arithmetic; eta/max_steps from
  `configs/scoring/default.json` with verified config hash and
  Decimal-from-literal parsing; ROUND_HALF_EVEN display strings (7 dp)
  beside exact `p/q` values.
- `scoring/diagnostics.py` — TZ 15.9 diagnostics (counts, breakdown,
  exact-match counts, evidence coverage, per-type recall, optimal-steps
  reporting, truncated/no-submit audit status that is never "OK",
  explicit NOT_AVAILABLE markers, experimental grounded score column),
  reward-property matrix builder and machine evaluator P1..P5.
- `scoring/exhaustive.py` — independent brute-force oracle (all partial
  matchings) for graphs up to 7x7; also returns the lexicographic best.
- `tests/scoring/` — 91 tests: canon (16), matcher predicate (14),
  sanity A-J + rules (15), order/tie-break (13), differential (4),
  properties + matrix (8), diagnostics (11).

## GitHub traceability

- Issues: #3 (contract integration blockers — referenced, not closed)
- PRs: this session's PR (Phase 6) from `arena/a3999087-genesis-hackathon-malika-nurzh`;
  base stack = PR #2 head `ef15218` (fast-forwarded; includes PR #1)
- Commits: see `docs/AGENT_REPORTS/2026-11-21/A3-phase-06.md`
- Branch: `arena/a3999087-genesis-hackathon-malika-nurzh`

## Verification

| Gate | Command | Result | Artifact |
|------|---------|--------|----------|
| Python 3.11 check | `make setup` | PASS (exit 0, Python 3.11.2; optional extras ABSENT) | stdout |
| Compile + import boundaries | `make lint` | PASS (exit 0, scan CLEAN REQ-ARC-001..007) | stdout |
| Full unit + contract + scoring tests | `make test` | PASS (exit 0, 131 tests OK; baseline 40 -> 131) | stdout |
| Property tests (stdlib fallback) | `make test-property` | PASS (exit 0, 3 tests OK) | stdout |
| Core rubric checks | `make verify-core` | PASS (exit 0, RC-001..003 PASS) | `artifacts/reports/latest/verify_summary.json` |
| Full verify | `make verify` | PASS (exit 0, RC-001..003 PASS) | `artifacts/reports/latest/verify_summary.json` |
| Aggregated report | `make report` | PASS (exit 0) | `artifacts/reports/latest/report_index.json` |
| Reward property matrix P1..P5 | `python3 -m unittest tests.scoring.test_reward_properties` | PASS (P1=4 checks, P2=2, P3=8, P4=1, P5=1; all PASS) | `docs/PHASE_REPORTS/PHASE-06-reward-matrix.json` |
| Differential matcher (60 graphs + 40 tie-break + 6 known + 10 oracle) | `python3 -m unittest tests.scoring.test_differential` | PASS | stdout |

Sanity values from TZ 15.6 pinned exactly: A R=49/50 (0.98), B R=391/600
(0.6516667), C R=39/50 (0.78), D R=99/100 (0.99), E/F/G R=0, H R=19/20
(0.95 with truncation flagged), I TP not inflated, J boundary exact.

## Failed or skipped checks

- `make docker-check`: NOT RUN (Docker unavailable in the session
  sandbox; affects only the Phase 16-style offline image check, not the
  Phase 6 gate). Reproduce with `make docker-check` where Docker exists.
- pytest/hypothesis/jsonschema suites: SKIPPED — optional extras are
  ABSENT (REQ-CONCON-003 behaviour: make verify does not fail and says
  so). Core stdlib tests are the required gate.
- GitHub branch protection / CI on the PR: see Git/GitHub section.

## Decisions and deviations

- D-06-00..D-06-05 in `docs/DECISIONS.md`; draft `docs/CR/CR-06-01.md`
  requests the A0 disposition of the parallel-branch contract freezes
  (issue #3). Phase 6 changed no frozen contract file.
- Deviation: `scoring/` may import `contracts` only (+stdlib); it does
  not use `seal/` yet (allowed direction, unused at this phase).

## Risks

- The official reward formula, match criteria, tolerance semantics and
  finding schema remain unconfirmed (Q-003/Q-005); the adapter layer
  (TZ 7.3) must absorb any organiser differences.
- Parallel branches carry conflicting v1.0.0 freezes (CR-05-01/CR-06-01);
  integration must follow the A0 decision before Phase 5/7 merge.
- Exact lexicographic refinement cost grows with candidate edges
  (bounded at 4096 with an explicit error); far above episode sizes.

## Next phase readiness

Phase 7 (FX/period-cutoff operators) and Phase 8 (verifier) do not
depend on the open contract question beyond what Phase 6 already marks
provisional; Phase 5 env reconciliation (issue #3) and the A0 contract
disposition should land before a combined release branch. The matcher
and reward are ready to score any episode whose truth is produced in the
frozen truth schema.

## Owner sign-off

Human owner sign-off pending (session agent A3 executed and verified).
