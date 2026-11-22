# TEST_QUALITY_REPORT — what the suite actually proves

Measured at commit `0afdbd8`, after all fixes.

## Headline numbers

| Suite | Command | Result |
|---|---|---|
| Full verification suite | `python3 -m unittest discover -s tests -t .` | **502 tests, 18 skipped, OK** |
| Official blocks 1–4 | `python3 -m unittest discover -s tests/official` | **55 tests, OK** |
| Mutation suite | `make mutation-test` | **26/26 killed (100.0%)** |
| Metamorphic | `make verify` → RC-011 | **7/7 transforms, 28 episode pairs** |
| Replay | `make replay-all` | **80/80 runs, 567 steps byte-identical** |
| Property tests | `make test-property` | 17 tests, 1 skip |

## Are the 18 skips honest?

Yes — all are declared bootstrap skips. The suite prints the reason for each,
e.g. `doc-claims: SKIPPED (bootstrap: no artifacts yet; authoritative check
runs in judge/verify.py after the gates)` and `release-audit: report absent -
integration checks skip explicitly (bootstrap position)`. No skip is counted
as a pass, and the authoritative version of each check is `make verify`
(12/12 PASS) and `make release-audit` (6/6 PASS).

## Test-quality defects found by this audit

### TQ-1 — A P0 shipped because an official test covered the wrong table

`test_C05_pagination_over_large_fixture_L_three_pages` read
`record_counts["invoices"]` (111 rows → offsets 50, 100) and never walked
`ledger` (214 rows → offsets 50, 100, 150, 200). The cursor defect
(BUG-TL-0002) lived at offset 200. The test asserted `pages >= 3` and passed.

Root cause: the test encoded the *example* ("три страницы") instead of the
*requirement* ("all source rows reachable"). Fixed by walking every canonical
table with per-table exact counts (BUG-TL-0004).

Lesson recorded in the registry: an official check that passes is only
evidence if it exercises the largest fixture the contract allows.

### TQ-2 — A security test passed for the wrong reason

`test_pagination_opaque_cursors_and_tamper_rejection` asserted that
`valid_cursor + "x"` is rejected. It passed on the old code because the old
`rsplit` happened to re-split the re-padded bytes — not because the token was
validated canonically. When BUG-TL-0002 was fixed the test started failing,
exposing BUG-TL-0003 (trailing garbage genuinely accepted).

This is the most dangerous class of test defect: a green test protecting a
real weakness by coincidence. Fixed with a canonical re-encode rule plus two
dedicated tests (`test_trailing_garbage_rejected`,
`test_non_canonical_trailing_bits_rejected`).

### TQ-3 — Three mutants silently disarmed by a refactor

Fixing BUG-TL-0001 removed the `f1_score` call from the reward path, so
MUT-07/08/13 — which patch `reward_mod.f1_score` — "survived" while the code
was actually correct. A mutation suite that patches a dead symbol reports a
false negative. Fixed by introducing `reward_metrics()` as the live seam and
re-pointing the three mutants. Mutation score 23/26 → 26/26.

Lesson: a mutation suite must be re-validated whenever the code it patches is
refactored; otherwise a falling score can be a *test* artifact and a rising
score can be meaningless.

## Are the tests meaningful, or just numerous?

Evidence that they are meaningful, not merely counted:

- **Every accepted bug has a test that fails on the old code.** Verified by
  `git stash push -- <file>` and re-running:
  - old `env/cursors.py` → `test_every_offset_round_trips` errors with
    `BAD_CURSOR` at offsets 1, 7, …; strengthened C05 fails at `ledger page 3`;
    `test_trailing_garbage_rejected` fails.
  - old `scoring/reward.py` → 8 reward-sanity vectors, P5, the unit-interval
    property and diagnostics fail.
- **Mutation kill rate 26/26** — every documented failure mode is reachable
  by at least one test.
- **Metamorphic 7/7** — invariance under ID remap / row permutation is
  checked behaviourally, not by asserting our own matcher agrees with itself.
- **Independent verifier in Block 2** — the gate uses `discover()` +
  `crosscheck()` (a separately implemented verifier), not the team matcher, so
  "our matcher agrees with our oracle" is not the only evidence.
- **Deterministic fault injection** — C18 uses a fake clock, not "run it on a
  slow laptop", matching the official requirement that the check be
  reproducible.

## Known test limitations

1. Coverage is behavioural, not line-coverage-measured; no coverage tool is
   installed and none is claimed.
2. Property-based tests use a fixed seed (`random.Random(777)`) so they are
   deterministic but not exhaustive. Hypothesis is optional and skipped in
   bootstrap.
3. Docker-based checks (`make docker-check`) could not run in this sandbox
   (no `docker` binary). They are therefore **UNVERIFIED** here, not PASS —
   see `REPRODUCIBILITY_AUDIT.md`.
4. The statistical shortcut audit is one seed; the AUC is reported as a
   measurement, not a guarantee.
