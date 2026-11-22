# BUG_REGISTRY — TwinLedger v3.0 forensic audit

Branch `arena/45dc3a73-genesis-hackathon-malika-nurzh` from `3a3988e`.
Registry maintained at commit `ca04f3f`.

Status vocabulary (fixed by the audit prompt):
`VERIFIED` (real run + artifact) · `IMPLEMENTED` · `PARTIAL` · `SKIPPED` ·
`BLOCKED` · `UNVERIFIED` · `FAILED`.
A bug is only `FIXED/VERIFIED` when a **regression test that fails on the old
code** passes on the new code.

---

## BUG-TL-0001 — Two competing reward implementations; the internal one is wrong

| Field | Value |
|---|---|
| Severity | **P0 — release blocker** |
| Category | Core correctness / duplicate implementation |
| Status | **VERIFIED FIXED** |
| Discovered by | Running the 11 published reward vectors against `scoring/reward.py` |
| Files affected | `scoring/reward.py`, `arena/autohacker.py`, `judge/mutation_suite.py`, `judge/robustness_audit.py`, `scoring/diagnostics.py` (P5 bound) |

### Symptom

`scoring/reward.py` implemented the **provisional** formula from Master TZ
assumption A-005:

```
R = max(0, F1 - eta * steps_used / max_steps)      eta = 0.05, max_steps = 100
```

while `scoring/official_scorer.py` — the module the jury actually reaches
through `judge_adapter.score_episode` — implemented the **official** formula
published on 2026-11-20:

```
return = clip([-1, 1], 2*F1 - 1 - 0.2 * inspection_steps / 100)
```

Measured divergence against the official vectors:

| Official test | F1 | steps | Official expected | Legacy produced |
|---|---:|---:|---:|---:|
| 1 | 1 | 10 | 0.98 | 0.995 |
| 2 | 0 | 10 | −1.0 | 0.0 |
| 3 | 1 | 10 | 0.98 | 0.995 |
| 4 | 0 | 10 | −1.0 | 0.0 |
| 5 | 2/3 | 10 | 47/150 | 0.6617 |
| 12 | 2/21 | 10 | −871/1050 | +0.0902 |
| 13 | 2/3 | 10 | 47/150 | 0.6617 |
| 14 | 1/2 | 10 | −0.02 | 0.4950 |
| 15 | 1 | 0 | 1.0 | 1.0 (only match) |
| 16 | 1 | 50 | 0.90 | 0.975 |
| 17 | 1 | 100 | 0.80 | 0.95 |

10 of 11 vectors wrong. Two further divergences:

1. **Negative rewards were impossible.** The legacy formula floored at 0, so a
   completely missed book scored `0.0` instead of `-1.0`. Official test 2 is
   an explicit `-1`.
2. **Empty-truth precision/recall.** Legacy `precision_score(0,0) = 1` and
   `recall_score(0,0) = 1`; official test 3 requires `P = R = 0` with `F1 = 1`.

### Impact

The published baselines were **not** affected (`tools/run_official_eval.py`
goes through `judge_adapter` → `official_scorer`; oracle 0.9920,
simple_reconciliation 0.9853, random −0.5060, mass_flagging −1.0000 are all
official-formula numbers). What *was* affected is every internal diagnostic
artifact: autohacker attribution rewards, the mutation suite's own arithmetic
checks, `judge/robustness_audit.py`, the reward-property matrix (P5), and the
`RewardBreakdown.eta`/`penalty` fields. All of these published numbers the
jury would never reproduce, and a reader comparing them to the official rubric
would conclude the environment was mis-scored.

### Root cause

The project shipped the official scorer in Phase 14 (RC-004) but never retired
the Phase 6 provisional reward module. Two modules, one formula each, no test
pinned them together. `tests/official/test_block3_scorer.py` covered the
correct one; `tests/scoring/*` covered the wrong one; nothing compared them.
This is exactly the "duplicate competing implementations" failure mode.

### Fix

- `scoring/reward.py` now delegates all arithmetic to
  `compute_official_metrics` through a single `reward_metrics()` function.
  No second formula exists in the tree.
- `RewardBreakdown.eta` reports the **applied** weight (0.2) and `penalty` the
  applied penalty, so no consumer can read a 0.05 bound off a breakdown.
- `precision_score` / `recall_score` keep the vacuous-truth convention because
  the generator cross-check (EXIT GATE 8) depends on it; the official
  `P = R = 0` rule applies to the reward path only. Documented in both
  docstrings and in `D-18-01`.
- `configs/scoring/default.json` is a **frozen contract** and is untouched
  (D-14-02). It still carries `eta: 0.05`; that key no longer influences
  anything. Recorded in `D-18-01` rather than silently re-frozen.

### Regression evidence

| Test | Fails on old code | Passes on new code |
|---|---|---|
| `tests/scoring/test_reward_sanity.py` (15 vectors, re-based + cited) | yes (8 vectors) | yes |
| `tests/unit/test_property.py::test_scoring_stays_in_unit_interval` | yes (asserted ≥ 0) | yes (asserts −1…1) |
| `tests/scoring/test_reward_properties.py::test_p5_*` | yes (0.05 bound) | yes (0.2 bound) |
| `tests/scoring/test_diagnostics.py` | yes | yes |
| Mutation suite MUT-07/08/13 | survived before | 26/26 killed |

### Follow-on defect found while fixing (same registry, separate ID)

Retiring the formula silently **disarmed three mutants**: MUT-07/08/13
patched `reward_mod.f1_score`, which was no longer on the reward path, so they
"survived" while the code was correct. Fixed by routing through
`reward_metrics()` and re-pointing the mutants. Mutation score restored from
23/26 to 26/26. This is recorded rather than hidden because a mutation suite
that patches a dead symbol gives false assurance.

---

## BUG-TL-0002 — Pagination cursors are unusable for ~6% of offsets

| Field | Value |
|---|---|
| Severity | **P0 — release blocker** (official C05) |
| Category | Core correctness / official contract C05 |
| Status | **VERIFIED FIXED** |
| Discovered by | Walking the official fixture **L** (214-row ledger) in pages of 50 |
| Files affected | `env/cursors.py` |

### Symptom

Walking the L fixture's `ledger` (214 rows) with `limit=50`:

```
page 0: n=50 next=eyJvIjo1MCwicSI6...
page 1: n=50 next=eyJvIjoxMDAsInEiOi...
page 2: n=50 next=eyJvIjoxNTAsInEiOi...
page 3: RESULT NULL, error={"code": "BAD_CURSOR",
                            "message": "cursor signature verification failed"}
```

Rows 200–213 were **unreachable**. Official C05 requires "при проходе нет
пропусков … Все исходные строки достижимы" (no gaps; all source rows
reachable).

### Root cause

```python
return base64.urlsafe_b64encode(raw + b"." + sig).decode("ascii")   # encode
raw, sig = decoded.rsplit(b".", 1)                                   # decode
```

The signature is 16 uniformly random HMAC bytes. The probability that at least
one of them equals the delimiter byte `0x2E` is
`1 - (255/256)^16 ≈ 6.5%`. For those tokens `rsplit` splits at the wrong
place, `raw` differs, and verification fails. Measured over offsets 0–999:
65 unusable offsets, the first at offset 4.

The bug is data-dependent, which is why it survived: whether a given page
fails depends on the HMAC of that offset. The official C05 test happened to
page `invoices` (111 rows → offsets 50 and 100 only), both of which were
lucky. `ledger` at offset 200 was not.

### Fix

Token layout is now `sig || raw` with a fixed-width prefix
(`CursorCodec._SIG_LEN = 16`), so **no byte value is ever significant**.
Delimiters are gone rather than escaped.

### Regression evidence

- `tests/env/test_cursor_codec.py` — 12 tests. `test_every_offset_round_trips`
  asserts all 1000 offsets decode correctly; on the old code it errors at
  offsets 1, 7, … with `BAD_CURSOR: cursor signature verification failed`.
- `tests/official/test_block1_contracts.py::test_C05_pagination_over_large_fixture_L_three_pages`
  was **strengthened** to walk every canonical table (`ledger`, `invoices`,
  `payments`, `fx`). On the old code it now fails at `ledger page 3` with
  `BAD_CURSOR`; before the strengthening it passed. The test was part of the
  defect: it only ever visited offsets that were lucky.
- End-to-end: 5 pages of 50/50/50/50/14, 214/214 rows, no duplicates.

### Artifact consequence (handled, not hidden)

Cursor tokens are embedded in the published
`artifacts/trajectories/trajectories.jsonl`. After the format change the old
file no longer replayed, so it was regenerated with `make official-eval`.
Verified that the regeneration changed **only** cursor tokens:

```
rows before/after: 80 80
rows differing beyond cursor tokens: 0
metrics identical: True
final_findings identical: True
initial_observation identical: True
```

Baselines are unchanged to the digit (oracle 1.0000/+0.9920/4.0,
simple_reconciliation 1.0000/+0.9853/7.3, random 0.2500/−0.5060/12.0,
mass_flagging 0.0000/−1.0000/1.0). `make replay-all` → PASS 80/80,
567 steps byte-identical.

---

## BUG-TL-0003 — Cursor tamper-evidence defeated by trailing base64 garbage

| Field | Value |
|---|---|
| Severity | **P1** (security / tamper evidence) |
| Category | Security |
| Status | **VERIFIED FIXED** |
| Discovered by | `tests/env/test_environment.py` failing after BUG-TL-0002 was fixed |
| Files affected | `env/cursors.py` |

### Symptom

`base64.urlsafe_b64decode` silently ignores trailing characters. Appending
`"x"` to a valid token therefore decodes to the original bytes and passes
signature verification:

```
suffix 'x' : decodes to 68 bytes, same as orig: True
suffix 'xy': decodes to 68 bytes, same as orig: True
```

The existing test asserted `valid_cursor + "x"` must be rejected. On the old
code it passed **by luck**: the old decoder's `rsplit` on the re-padded bytes
happened to produce a different `raw`. This is a real defect that an
accidental test was masking.

### Root cause

Cursor verification checked the HMAC of the decoded payload but never checked
that the presented token was the canonical encoding of that payload. Trailing
garbage, alternate alphabets and non-canonical trailing bits were all
accepted.

### Fix

`decode()` now requires `base64.urlsafe_b64encode(decoded).decode() == token`
before any other check. This rejects trailing garbage, stray padding,
alternate alphabets and non-canonical trailing bits in one rule.

### Regression evidence

- `test_trailing_garbage_rejected` — suffixes `x`, `xy`, `=`, `..`, `A`,
  `AAA`. Fails on old code, passes on new.
- `test_non_canonical_trailing_bits_rejected` — flips bits that base64
  discards.
- `tests/env/test_environment.py::test_pagination_opaque_cursors_and_tamper_rejection`
  passes for the right reason now.

---

## BUG-TL-0004 — Official C05 test did not cover the documented L fixture completely

| Field | Value |
|---|---|
| Severity | **P1** (test quality — allowed a P0 to ship) |
| Category | Test quality / traceability |
| Status | **VERIFIED FIXED** |
| Discovered by | Root-cause analysis of BUG-TL-0002 |
| Files affected | `tests/official/test_block1_contracts.py` |

### Symptom

`test_C05_...` read `record_counts["invoices"]` and walked only `invoices`.
The L fixture has `ledger: 214, invoices: 111, payments: 103, fx: 146`; the
largest table — the one that actually needs a fourth page — was never walked.
The test asserted `pages >= 3` and passed while a fourth-page cursor failed.

### Root cause

The test mirrored the wording "три страницы" (three pages) from the official
text and stopped at the minimum. The binding requirement is "all source rows
reachable", which is a property of **every** table.

### Fix

The test now walks every canonical table with a declared ID field, asserts
per-table exact row counts and zero duplicates, requires all four tables to be
walkable, and caps page count to catch non-termination.

### Regression evidence

Old code + strengthened test → `AssertionError: {'code': 'BAD_CURSOR', …
'ledger page 3'}`. New code → PASS.

---

## BUG-TL-0005 — The reward-property matrix published a formula nobody implements

| Field | Value |
|---|---|
| Severity | **P1** (published evidence contradicts the live implementation) |
| Category | Evidence provenance / duplicate published contract |
| Status | **VERIFIED FIXED** |
| Discovered by | Phase 17 deep audit: reading every *published* artifact against `D-18-01` |
| Files affected | `scoring/diagnostics.py`, `scoring/official_scorer.py`, `scoring/reward.py`, `tools/verify_doc_claims.py` |

### Symptom

`artifacts/reports/latest/reward_property_matrix.json` carried

```
"formula": "R = max(0, F1 - eta * steps_used / max_steps)",
"provisional": true
```

while every **number** in the same file had been computed by the official
implementation since `D-18-01` (BUG-TL-0001): the matrix's own rows report
`eta_exact: "1/5"` and rewards such as `24/25` for a clean honest run at 20
steps, which is `clip([-1,1], 2*F1 - 1 - 0.2*steps/100)` and **not**
`max(0, F1 - eta*steps/max_steps)` with `eta = 0.05` (which would be `0.99`).

### Impact

The artifact told a reader that the published reward-property evidence
measures a reward implementation that no longer exists — the exact
misinformation that made BUG-TL-0001 dangerous, but one level up: the numbers
were right and the *label* was wrong. A jury member comparing the matrix
with `docs/API_USAGE.md` would have found two different formulas and had no
way to tell which one the code implements.

### Root cause

The formula string was a **second literal**. `D-18-01` migrated the
arithmetic and left the published text behind; nothing compared the artifact
to the implementation, because `C-REWARD` only scanned prose (`DOC_SCAN`),
never the generated reports.

### Fix

- `scoring.official_scorer.official_formula_text()` renders the formula
  **from the live constants** (`OFFICIAL_STEP_PENALTY_WEIGHT`,
  `OFFICIAL_STEP_BUDGET`); `scoring.reward.FORMULA` is that function's
  result, and `scoring.diagnostics` publishes the same string with
  `provisional: false`.
- `C-REWARD` now also audits `artifacts/reports/latest/*.json`: the
  superseded formula may not appear, the matrix must publish the live
  formula and `provisional: false`.

### Regression evidence

| Test | Fails on old code | Passes on new code |
|---|---|---|
| `tests/scoring/test_formula_provenance.py::test_matrix_publishes_the_live_formula` | yes (old formula string) | yes |
| `tests/scoring/test_formula_provenance.py::test_matrix_is_not_provisional` | yes (`True`) | yes |
| `tests/scoring/test_formula_provenance.py::test_no_published_artifact_carries_the_superseded_formula` | yes (artifact quoted it) | yes |
| `tests/scoring/test_reward_properties.py::test_matrix_artifact_written` | yes | yes |
| `tools/verify_doc_claims.py` `C-REWARD` (artifact branch) | yes (`ARTIFACT_FORMULA_STALE`) | yes |

---

## BUG-TL-0006 — The robustness report claimed a scorer it does not use

| Field | Value |
|---|---|
| Severity | **P2** (published evidence states a false provenance) |
| Category | Evidence provenance |
| Status | **VERIFIED FIXED** |
| Discovered by | Phase 17 deep audit: same sweep as BUG-TL-0005 |
| Files affected | `judge/robustness_audit.py` |

### Symptom

`artifacts/reports/latest/robustness_report.json` carried

```
"score_contract": "scoring.reward (internal provisional; not official_scorer)"
```

### Impact

Since `D-18-01`, `scoring.reward` **is** a thin view over
`scoring.official_scorer`; there is no second scorer. The report therefore
told the reader that its reward column came from a provisional internal
implementation that the jury does not use — while in fact it came from the
one implementation the jury uses. The Phase 11 robustness evidence
(`24` twin pairs, honest-policy reward delta `0`) is valid; only its stated
provenance was wrong.

### Root cause

The string was written when two scorers existed and was never revisited when
`D-18-01` removed one of them.

### Fix

`judge/robustness_audit.SCORE_CONTRACT` is derived from the live module and
names `scoring.official_scorer` plus the live formula; the report keeps
`separated_from_official_score: true` and adds `score_contract_note`
("internal robustness measurement, not a jury score").

### Regression evidence

| Test | Fails on old code | Passes on new code |
|---|---|---|
| `tests/scoring/test_formula_provenance.py::test_score_contract_names_the_single_implementation` | yes | yes |
| `tools/verify_doc_claims.py` `C-REWARD` (artifact branch, `ARTIFACT_SCORE_CONTRACT_STALE`) | yes | yes |

---

## BUG-TL-0007 — A resolved protocol question was still described as open in the matcher

| Field | Value |
|---|---|
| Severity | **P3** (stale internal documentation) |
| Category | Documentation drift |
| Status | **VERIFIED FIXED** |
| Discovered by | Phase 17 deep audit: sweep for "provisional"/"pending" wording after `Q-005` was resolved on 2026-11-20 |
| Files affected | `scoring/matcher.py` |

### Symptom

The module docstring opened with

```
Match predicate (TZ 15.2, provisional pending official contract Q-005):
```

while `docs/QUESTIONS.md` records `Q-005` (official reward formula & clean-book
rule) as **RESOLVED** on 2026-11-20, and the predicate it documents is the one
the official spec fixed.

### Impact

Low: the code was correct and the docstring described the predicate
correctly. But a reader checking the question log would have found the code
claiming to wait for a contract that had arrived, which is exactly the kind of
stale "provisional" wording that `D-18-01` had to clean out of the
jury-facing docs.

### Fix

The docstring now states that the predicate is fixed by the official contract
of 2026-11-20 (`Q-005` RESOLVED) and is no longer provisional.

### Regression evidence

No behavioural test is applicable (documentation-only). The Phase 17 sweep
records the sweep command and its empty result; the general guard against
this class is `C-REWARD` (prose) plus the artifact sweep in
`tests/scoring/test_formula_provenance.py`.

---

## BUG-TL-0008 — The documentation gate's artifact contract named a file nobody produces

| Field | Value |
|---|---|
| Severity | **P2** (the documentation gate could not tell truth from fiction) |
| Category | Verification gate / phantom path |
| Status | **VERIFIED FIXED** |
| Discovered by | Phase 17 deep audit: reading `tools/verify_doc_claims.py` `C-PATHS` against the actual producers |
| Files affected | `tools/verify_doc_claims.py`, `tests/judge/test_doc_claims.py` |

### Symptom

`C-PATHS` compares the file paths published in the documentation with the
filesystem. Its contract for the generated directories was a hand-written
list:

```python
extra = {
    "doc_claims_report.json",
    "release_audit.json",
    "replay_all_report.json",   # no producer writes this file
    "official_eval_summary.json",
    "performance_report.json",
}
```

Two consequences:

1. `replay_all_report.json` **does not exist** — `make replay-all` writes
   `artifacts/reports/release/trajectory_replay.json`. A document citing the
   real file would have been reported as a *phantom path*, and the contract
   advertised a file that is never produced.
2. `reward_property_matrix.json` was **missing** from the contract, although
   it is part of the published evidence set (20 artifacts, `D-15-03`) and is
   written by `scoring.diagnostics.build_reward_property_matrix`. A document
   citing it was falsely reported as a phantom path as well — the gate was
   wrong in both directions.

### Impact

The documentation gate either blocked a correct document or accepted a
document naming a file that does not exist. It made `make docs-verify`
unreliable exactly where it claims to be a gate: the set of published
artifacts.

### Root cause

The contract was a second literal, maintained by hand, while the producers
were code. Nothing compared the two.

### Fix

The contract is now **derived from the producers**:

- the `artifacts/reports/latest/` set is read out of
  `judge/verify.py::REQUIRED_FULL_ARTIFACTS` (unchanged) and explicitly
  extended with `reward_property_matrix.json`, whose producer is the
  reward-property suite, not `judge/verify.py`;
- the other directories name exactly what their producers write:
  `doc_claims_report.json`, `release_audit.json` **and**
  `trajectory_replay.json` (not `replay_all_report.json`),
  `official_eval_summary.json`, `trajectories.jsonl`.

### Regression evidence

`tests/judge/test_doc_claims.py::test_generated_artifact_contract_matches_the_producers`
builds the contract and compares it with the file names the producers
actually write; it fails on the old contract (`replay_all_report.json`
missing / `reward_property_matrix.json` absent) and passes on the new one.

---

## BUG-TL-0009 — A malformed workflow file silently disabled CI

| Field | Value |
|---|---|
| Severity | **P1** (the CI gate disappeared; nothing in the repository failed) |
| Category | Release infrastructure / YAML |
| Status | **VERIFIED FIXED** |
| Discovered by | Phase 17: every push of the branch ran a workflow with **zero jobs** and failed in 0 s |
| Files affected | `.github/workflows/ci.yml`, `tools/check_workflows.py`, `tests/judge/test_workflows.py`, `Makefile` |

### Symptom

The Phase 17 evidence step was added to the CI workflow as

```yaml
- name: Evidence freeze (Phase 17: the committed archive must match the tree)
  run: make evidence-verify
```

A **plain (unquoted) YAML scalar may not contain a colon followed by a
space**: YAML reads `Phase 17: the committed archive must match the tree`
as a mapping, not as text. The whole file therefore stopped being valid
YAML.

### Impact

GitHub created a run for every push, the run failed **immediately with zero
jobs**, and the only hint was "This run likely failed because of a workflow
file issue". Nothing in the repository failed, because nothing in the
repository ran: the twelve Judge Kit gates, the offline container check and
the new evidence gate all silently disappeared, on four consecutive pushes.
A reviewer looking only at the repository would have seen a green branch.

### Root cause

A step *name* was edited by hand, and nothing in the repository parses the
workflow files. The CI configuration was the one artifact that was never
checked — the one artifact whose failure removes the checking.

### Fix

- The step name no longer contains a colon (`Phase 17 - the committed
  archive must match the tree`).
- New `tools/check_workflows.py` (stdlib-only, offline) parses the workflow
  files: a full YAML parse when PyYAML is importable, plus heuristics that
  always run (no unquoted `": "`, no tab indentation, a `jobs:` mapping
  must exist). The other YAML files of the repository
  (`docker-compose.yml`, `spec/*.yaml`) are scanned with the same
  heuristics.
- It runs in `make lint` (and therefore in CI) and in
  `tests/judge/test_workflows.py` (13 tests), so the hazard is caught
  **before** a push, not after four of them.

### Regression evidence

| Test | Fails on old code | Passes on new code |
|---|---|---|
| `tests/judge/test_workflows.py::test_unquoted_colon_space_is_flagged` | yes (no checker existed) | yes |
| `tests/judge/test_workflows.py::test_repository_workflows_are_well_formed` | yes (the broken file) | yes |
| `tests/judge/test_workflows.py::test_tab_indentation_is_flagged` | yes | yes |
| `tools/check_workflows.py` on the broken step name | reports the exact line | PASS |

---

## Summary

| ID | Severity | Component | Status |
|---|---|---|---|
| BUG-TL-0001 | P0 | `scoring/reward.py` | VERIFIED FIXED |
| BUG-TL-0002 | P0 | `env/cursors.py` | VERIFIED FIXED |
| BUG-TL-0003 | P1 | `env/cursors.py` | VERIFIED FIXED |
| BUG-TL-0004 | P1 | official C05 test | VERIFIED FIXED |
| BUG-TL-0005 | P1 | `scoring/diagnostics.py` (published formula) | VERIFIED FIXED |
| BUG-TL-0006 | P2 | `judge/robustness_audit.py` (score contract) | VERIFIED FIXED |
| BUG-TL-0007 | P3 | `scoring/matcher.py` (docstring) | VERIFIED FIXED |
| BUG-TL-0008 | P2 | `tools/verify_doc_claims.py` (artifact contract) | VERIFIED FIXED |
| BUG-TL-0009 | P1 | `.github/workflows/ci.yml` (malformed YAML disabled CI) | VERIFIED FIXED |

No claim is made that no bugs remain. Checks that were executed without
finding a defect are listed in `FIX_VERIFICATION_MATRIX.md`, and residual
limitations are listed in `FINAL_QUALITY_REPORT.md`.
