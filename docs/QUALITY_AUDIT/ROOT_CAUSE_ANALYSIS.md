# ROOT_CAUSE_ANALYSIS — why these four defects existed

The four defects are not four unrelated mistakes. They reduce to **three**
systemic causes, each of which is cheap to prevent and was not prevented.

---

## RC-A — A superseded implementation was never retired

**Defects:** BUG-TL-0001 (P0), and the disarmed mutants that followed it.

**Mechanism.** Phase 6 shipped a reward module against a *provisional*
formula (`A-005`). Phase 14 added the official scorer for the jury adapter.
The old module was left in place because other callers still imported it, and
nothing compared the two. So the tree carried one correct formula and one
wrong formula, each with its own green test suite.

**Why nobody noticed.**

- The correct formula was tested by `tests/official/` (Block 3, 32 tests).
- The wrong formula was tested by `tests/scoring/` (52 tests) — against its
  own expectations, so it always passed.
- The two suites never met. No test asserted "the internal reward equals the
  official reward".
- The published baselines happened to come from the *correct* path
  (`run_official_eval` → `judge_adapter`), so the visible numbers were right
  and the file-level error stayed invisible.

**Prevention now in place.**

- One implementation (`compute_official_metrics`); `reward.py` delegates.
- The official vectors are asserted through the *internal* API too
  (`test_reward_sanity.py` cites vectors 1/2/3/5/13/14/15/16/17).
- `D-18-01` records that a second formula may not exist.

**Generalisation.** When a provisional implementation is superseded, deletion
is part of the change. "Keep both, they both pass" is how a project ends up
publishing two different answers to the same question.

---

## RC-B — A test encoded the example, not the requirement

**Defects:** BUG-TL-0004 (P1), which allowed BUG-TL-0002 (P0) to ship.

**Mechanism.** The official text says the L fixture must need "three pages".
The test walked `invoices` (111 rows) and asserted `pages >= 3`. The binding
requirement is different: *all source rows reachable*. The L fixture's largest
table is `ledger` (214 rows), which needs five pages — and it was never
walked.

**Why the bug was data-dependent.** The cursor defect only fires when the
16-byte HMAC of a given offset contains the delimiter byte. Offsets 50 and 100
(walked) were lucky; offset 200 (never walked) was not. So the test's coverage
gap and the bug's randomness lined up to hide each other.

**Prevention now in place.**

- C05 walks every canonical table with per-table exact counts, zero-duplicate
  assertions, and a non-termination cap.
- `tests/env/test_cursor_codec.py` sweeps *offsets* 0–999 directly, which is
  the property the bug violated, independent of any fixture's luck.

**Generalisation.** For every "≥ N" requirement, ask which instance is the
*worst* one, and test that. A minimum is satisfied by luck; a maximum is not.

---

## RC-C — A green test protected a weakness by coincidence

**Defects:** BUG-TL-0003 (P1).

**Mechanism.** The tamper test appended `"x"` to a valid cursor and asserted
rejection. On the old code this passed — not because tokens were validated
canonically, but because the old `rsplit` re-split the re-padded bytes and the
signature check failed for an unrelated reason. When RC-B's fix changed the
token layout, the accidental rejection disappeared and the test went red,
revealing that trailing garbage was genuinely accepted.

**Why this is the most dangerous class.** A test that passes for the wrong
reason is worse than no test: it produces confidence and blocks investigation.
The symptom here was lucky — the failure surfaced because the code changed
underneath it. In a codebase where that code did *not* change, the weakness
would still be live and invisible.

**Prevention now in place.**

- Decoding requires the token to re-encode to itself byte for byte — a
  property-based rule rather than a list of rejected suffixes.
- Two dedicated tests (`test_trailing_garbage_rejected`,
  `test_non_canonical_trailing_bits_rejected`) name the property, so a future
  refactor cannot satisfy them by accident.

**Generalisation.** Assert the *property*, not one example of it. "This token
is rejected" can pass by luck; "every non-canonical encoding is rejected" and
"this exact token re-encodes to itself" cannot.

---

## RC-D — A mutation suite can report false negatives after a refactor

**Defects:** none shipped, but three mutants were silently disarmed.

**Mechanism.** MUT-07/08/13 patch `reward_mod.f1_score`. Once `compute_reward`
stopped calling `f1_score`, the patched symbol was dead code, so the mutants
"survived" — the suite reported 23/26 while the code was correct.

**Prevention now in place.** A named seam (`reward_metrics`) exists on the real
reward path and the mutants target it; the suite is back to 26/26. The reason
is recorded in `BUG_REGISTRY.md` so the next agent does not read "26/26" as a
static fact.

**Generalisation.** A mutation score is only meaningful for the code currently
on the execution path. Re-run it after any refactor that moves a seam.

---

## Cross-cutting observation

Three of the four defects were **invisible to the official test suite**, and
all three became visible only by executing the *contract itself* (walking the
real L fixture; computing the published reward vectors by hand) rather than by
running the existing tests. That is the single most useful lesson of this
audit: a green official suite is evidence about the tests' coverage as much as
about the code.
