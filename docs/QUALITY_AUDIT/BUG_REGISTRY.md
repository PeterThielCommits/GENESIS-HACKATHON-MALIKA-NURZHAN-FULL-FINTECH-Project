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

## BUG-TL-0010 — Root-anchored `.dockerignore` rules let stale bytecode and secrets into the image

| Field | Value |
|---|---|
| Severity | **P1** (the submission image was not reproducible and could carry key material) |
| Category | Container / build context |
| Status | **VERIFIED FIXED** |
| Discovered by | Phase 18: computing the *effective* build context with Docker's own path semantics |
| Files affected | `.dockerignore`, `tools/docker_context.py`, `tools/container_local_check.py`, `tests/judge/test_docker_hardening.py` |

### Symptom

`.dockerignore` contained `__pycache__`, `.env`, `*.pem`, `*.key` and `.venv`.
Docker anchors **every** pattern at the context root, so `__pycache__` matches
only `<root>/__pycache__` - never `<root>/contracts/__pycache__`. The same
holds for the other root-anchored rules.

Measured on this repository with the old rules: the build context contained
**750 files, of which 197 were stale `.pyc` files** from nested
`__pycache__` directories. A nested `deploy/prod.pem` or `service/.env` would
equally have entered the image.

### Impact

* the image was not byte-reproducible: the context depended on whatever
  bytecode happened to exist in the developer's working tree;
* stale `.pyc` files can shadow the sources inside a read-only runtime;
* the same anchoring gap applied to the secret patterns, so a key file in a
  subdirectory would have been baked into the published image.

### Root cause

The rules were written as if they were shell globs ("match any directory"),
and the earlier fix for `D-16-02` (the depth-2 `sealed/` layout) only added
the missing *depths* for the episode rules - the anchoring rule itself was
never checked against Docker's real semantics.

### Fix

* Every nested rule now uses an explicit `**/` prefix
  (`**/__pycache__`, `**/*.py[cod]`, `**/.env`, `**/*.pem`, `**/*.key`,
  `**/.venv`, `**/.git`, ...).
* New `tools/docker_context.py` implements Docker's path semantics (root
  anchoring, `*` vs `**`, directory inheritance, last match wins) so the
  **effective** build context can be computed instead of guessed.
* `tools/container_local_check.py` computes the effective context and refuses
  to run when it contains sealed truth, key material, VCS metadata or stale
  bytecode.
* The compose file and the Dockerfile keep their own, stricter contracts.

### Regression evidence

| Test | Fails on old code | Passes on new code |
|---|---|---|
| `tests/judge/test_docker_hardening.py::test_nested_bytecode_is_excluded` | yes (the old rules matched nothing nested) | yes |
| `tests/judge/test_docker_hardening.py::test_root_anchored_patterns_are_not_used` | yes (`__pycache__`, `.env`, `*.pem`, `*.key` were root-anchored) | yes |
| `tests/judge/test_docker_hardening.py::test_context_has_no_stale_bytecode` | yes (197 `.pyc` files) | yes |
| `tests/judge/test_docker_hardening.py::test_context_contains_every_tracked_file_that_is_not_excluded` | n/a (the context did not exist as a computable object) | yes |
| measured effective context | 750 files (197 stale `.pyc`) | 556 files, 0 stale `.pyc` |

---

## BUG-TL-0011 — The base image was a floating tag, so the image was not reproducible

| Field | Value |
|---|---|
| Severity | **P1** (TZ 22.4 requires the base image digest to be pinned) |
| Category | Container / reproducibility |
| Status | **VERIFIED FIXED** |
| Discovered by | Phase 18: TZ 22.4 audit ("pin the base image digest, the Python patch version, the package versions and the commands") |
| Files affected | `Dockerfile`, `docs/EVIDENCE/docker-build-info.json`, `tools/docker_build_info.py`, `tools/release_audit.py`, `judge/performance_and_deps.py`, `tests/judge/test_docker_hardening.py` |

### Symptom

`FROM python:3.11-slim-bookworm` - a moving tag. Two builds a week apart
produce different images, and the Python patch version inside the image is
whatever the tag currently points at.

### Impact

The submission could not claim a reproducible verification image, and the
rubric criterion "versions of the configurations" (Block 5, 0/1/2) was only
partially met: the *code* and the *benchmark configs* were pinned, but not
the environment the code runs in.

### Root cause

The Dockerfile was written for "run the verification", not for "the
verification environment is itself a pinned artifact". Nothing in the
repository recorded the base image, its digest or the Python patch version it
contains.

### Fix

* `ARG BASE_IMAGE="python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b"`
  - the multi-platform (`linux/amd64` + `linux/arm64`) manifest of
  **Python 3.11.16 / Debian bookworm** - and `FROM ${BASE_IMAGE}`.
* The image writes its **own provenance record**
  (`/usr/local/share/twinledger/build_info.json`): base image, base digest,
  CPython patch version, Debian release, and the versions of the two Debian
  packages it installs.
* `docs/EVIDENCE/docker-build-info.json` records the pinned facts; the
  release audit checks that the Dockerfile and the record agree.
* `python3 tools/docker_build_info.py resolve` resolves the upstream tag
  digest and reports drift; the CI job `base-image` runs it on every commit
  and publishes the result as a commit status and an annotation.
* The dependency audit (`judge/performance_and_deps.py`) now parses the
  declared base image instead of matching a literal `FROM python:3.11`
  substring (see BUG-TL-0013).

### Regression evidence

| Test | Fails on old code | Passes on new code |
|---|---|---|
| `tests/judge/test_docker_hardening.py::test_dockerfile_pins_the_base_image_by_digest` | yes (no digest) | yes |
| `tests/judge/test_docker_hardening.py::test_committed_build_info_matches_the_dockerfile` | yes (no record existed) | yes |
| `tools/release_audit.py` SUBMISSION check | yes (no digest check) | yes |
| `python3 tools/docker_build_info.py verify --require-build-info` | FAIL ("not pinned") | PASS |

---

## BUG-TL-0012 — The Compose profile had no process/file-size limits and one unwritten path

| Field | Value |
|---|---|
| Severity | **P2** (TZ 16.2 resource limits "where supported"; one writable path was not isolated) |
| Category | Container / hardening |
| Status | **VERIFIED FIXED** |
| Discovered by | Phase 18: container hardening audit |
| Files affected | `docker-compose.yml`, `tools/check_compose_profile.py`, `tests/judge/test_docker_hardening.py`, `Makefile` |

### Symptom

`docker-compose.yml` declared `network_mode: none`, `read_only: true`,
`cap_drop: ALL`, `no-new-privileges`, `user: 10001:10001`, `cpus` and
`mem_limit` - but **no** `pids_limit`, **no** `ulimits`, and the `verify`
service did not mount `/app/artifacts/reports/doc_claims` as tmpfs (the
Makefile's container run does). Nothing checked the file: CI never executes
it.

### Impact

A judge starting the Compose profile would run without a process cap or a
file-size cap, and one of the three writable report paths would not be
isolated from the read-only image tree - the write would fail at runtime
instead of being redirected to tmpfs.

### Root cause

The Compose file was written by hand and reviewed by eye; the CI container
run (a `docker run` command line) is the artifact CI actually exercises, so
the Compose drift was invisible.

### Fix

* Every service now declares `pids_limit` and an `fsize` ulimit, and the
  `verify` service mounts all three writable paths as tmpfs.
* New `tools/check_compose_profile.py` parses the file with a stdlib-only
  YAML-subset reader and checks the whole hardening contract per service;
  it runs in `make lint` (and therefore in CI) and is covered by
  `tests/judge/test_docker_hardening.py`, including negative cases (a
  service that regains network access, root, a bind mount or a missing limit
  must be reported).

### Regression evidence

| Test | Fails on old code | Passes on new code |
|---|---|---|
| `tests/judge/test_docker_hardening.py::test_compose_profile_satisfies_the_hardening_contract` | yes (no `pids_limit`, no `ulimits`, missing tmpfs) | yes |
| `tests/judge/test_docker_hardening.py::test_checker_detects_a_service_that_regains_network_access` | yes (no checker existed) | yes |
| `tests/judge/test_docker_hardening.py::test_checker_detects_a_bind_mount` | yes | yes |
| `make lint` | PASS (the file was never parsed) | PASS (and now proves the contract) |

---

## BUG-TL-0013 — The dependency audit matched the Dockerfile with a literal substring

| Field | Value |
|---|---|
| Severity | **P2** (a false FAIL of a release gate; caught before release) |
| Category | Judge Kit / audit |
| Status | **VERIFIED FIXED** |
| Discovered by | Phase 18: the new container-equivalent run reported `RC-012 FAIL` with `step_p99=0.09ms` (the metrics were *inside* the targets) |
| Files affected | `judge/performance_and_deps.py`, `tests/judge/test_docker_hardening.py` |

### Symptom

`_audit_dependencies()` decided whether the image was pinned with

```python
pinned_py311 = "FROM python:3.11" in dockerfile_txt
```

After the Dockerfile moved to `ARG BASE_IMAGE=...` + `FROM ${BASE_IMAGE}`
(TZ 22.4 pinning), the literal substring disappeared and the audit reported
`dockerfile_python_311_pinned: false` -> `status: FAIL` -> the release gate
`RC-012` failed even though the *measured* performance and dependency facts
were all inside their targets.

### Impact

Left unfixed, the release would have been blocked by a gate that measured
the wrong thing: the audit verified a *spelling* of the Dockerfile instead of
the property it cares about.

### Root cause

The check was a text search written before the Dockerfile had a build
argument; it was never re-checked against a changed Dockerfile.

### Fix

`judge/performance_and_deps.py` now parses the declared base image
(`ARG BASE_IMAGE` or a literal `FROM`), derives the image name and the
digest from it, and records both plus the image's Python patch version and
the package versions in `dependency_report.json`.

### Regression evidence

| Test | Fails on old code | Passes on new code |
|---|---|---|
| `judge/performance_and_deps.py` on the ARG-based Dockerfile | `status: FAIL`, `dockerfile_python_311_pinned: false` | `status: PASS`, `dockerfile_base_image_digest_pinned: true` |
| `tests/judge/test_docker_hardening.py::test_static_verify_passes_for_the_committed_state` | yes (the audit reported the unpinned image) | yes |

---

## BUG-TL-0014 — The CI package-version drift check could never fire

| Field | Value |
|---|---|
| Severity | P2 |
| Component | `tools/docker_build_info.py` (`publish`) and `docs/EVIDENCE/docker-build-info.json` |
| Status | VERIFIED FIXED |
| Discovered by | Phase 18: reading back the CI-built image's own provenance record |

### Symptom

`tools/docker_build_info.py publish` compares the image's own build record
with the committed `docs/EVIDENCE/docker-build-info.json` and reports a
difference. The comparison read the committed file's `apt_packages` map — a key
the committed record never had (it only listed `apt_packages_required`, the
package *names*). The loop therefore always found an empty expectation and
skipped the check: the drift comparison for the Debian package versions was a
silent no-op. A mirror that started serving a different `util-linux` would
have produced no signal at all, even though TZ §22.4 asks for the package
versions to be recorded.

### Impact

Low, but it is a *reporting* defect in the layer whose whole job is to report
drift: the recorded-version check was structurally unreachable, so the
"CI says so out loud" property was not actually true for the two packages.

### Root cause

The committed record was written from the *declared* contract (which packages
the image installs) rather than from the *observed* contract (which versions
the built image actually contains), and the two were never separated in the
schema.

### Fix

The schema now separates them:

* `apt_packages_required` — the names the image must install (unchanged);
* `apt_packages_observed` — the versions read back from the CI-built image
  (`make 4.3-4.1`, `util-linux 2.38.1-5+deb12u3`, CI run `45044654821`).

`publish` now compares against `apt_packages_observed` and **splits the
outcome by what is actually pinned**:

* a changed base image, digest or Python patch version is a **hard failure**
  — the image is no longer the released one (`DRIFT`);
* a changed package version is a **warning** — the versions are resolved by
  `apt` at build time and are deliberately not pinned (limitation L11), so a
  moved Debian mirror must be reported, not fail the build.

`docker_build_info.py verify` and the release audit now require that every
tracked package has a *real* recorded version, and reject the literal
`"unknown"`, so a missing observation can never be published as a fact.

### Regression evidence

| Test | Fails on old code | Passes on new code |
|---|---|---|
| `tests/judge/test_docker_hardening.py::test_committed_build_info_publishes_the_observed_package_versions` | yes (the record had no observed versions) | yes |
| `tests/judge/test_docker_hardening.py::test_static_verify_rejects_an_unrecorded_package_version` | yes (the check could not fail) | yes |
| `tools/docker_build_info.py verify --require-build-info` | PASS with no version recorded | PASS with the versions recorded |
| `make release-audit` (SUBMISSION check) | PASS without any observed version | PASS, and now requires a real version per package |

---

## BUG-TL-0015 — A masked CI failure: an unusable namespace was a FAIL, and the step hid it

| Field | Value |
|---|---|
| Severity | P1 |
| Component | `tools/container_local_check.py`, `.github/workflows/ci.yml` |
| Status | VERIFIED FIXED |
| Discovered by | Phase 18 close-out: reading the check-run annotations of the *successful* `docker-offline` job |

### Symptom

The CI job `docker-offline` reported **success** while one of its steps had
failed with exit code 1. GitHub recorded the raw exit code as a stray
`Process completed with exit code 1` annotation attached to a green job, so the
only trace of the failure was an annotation nobody reads.

Two constructs hid it:

* the container-equivalent step carried `continue-on-error: true`, and
* the tool it ran reported a host that *forbids* unprivileged user namespaces
  as a generic **FAIL** (exit 1) instead of an explicit *skip*.

On the GitHub-hosted runner (Ubuntu 24.04) the AppArmor policy
`kernel.apparmor_restrict_unprivileged_userns=1` refuses
`unshare --map-root-user --mount --net` with `Operation not permitted`, so the
step could never do its work there. Measured evidence: the step's start and
completion timestamps are **identical** (zero seconds) in every successful job,
while a genuine run of the same tool takes 87-154 seconds. Injecting the
refusal locally reproduces the failure in 1.2 seconds.

### Impact

A real, reproducible failure was invisible: the CI summary said green, the
release evidence said green, and the only signal was an error annotation on a
successful job. The namespace-equivalent validation never ran in CI, and the
report said nothing about it. Any *future* failure of that step would have
been hidden the same way.

### Fix

* `tools/container_local_check.py` now **probes** the host first, with the same
  namespace recipe the run uses (unprivileged user namespace + mount + network
  namespace + the uid/gid mapping). A refusal that is environmental (EPERM,
  EACCES, ENOSYS, an AppArmor policy, a util-linux that is too old for
  `--map-user`) is reported as **UNSUPPORTED** — an explicit skip with a
  reason and exit code **2** — never a FAIL and never a PASS. A failure the
  probe cannot explain stays a FAIL (exit code 1).
* The CI step handles the three outcomes explicitly: `0` = PASS,
  `2` = SKIPPED (a `::notice::` annotation and a job-summary line), anything
  else = `::error::` **and the step fails**. `continue-on-error` is gone.
* The workflow now tries to enable unprivileged user namespaces on the runner
  (`sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`) so the real
  validation runs where the environment permits it, and reports whether that
  worked.
* The evidence artifact records the probe result and the reason, so a skipped
  check can never be read as a passed one (`REQ-JUDGE-003`).

### Regression evidence

| Test | Fails on old code | Passes on new code |
|---|---|---|
| `tests/judge/test_ci_masking.py::test_eperm_is_an_environmental_refusal` | yes (the refusal was not classified) | yes |
| `tests/judge/test_ci_masking.py::test_a_refused_namespace_is_a_skip_not_a_failure` | yes (the run reported FAIL) | yes |
| `tests/judge/test_ci_masking.py::test_unsupported_exits_two` | yes (exit 1) | yes (exit 2) |
| `tests/judge/test_ci_masking.py::test_a_workload_failure_is_a_real_failure` | yes | yes (still a FAIL) |
| `tests/judge/test_ci_masking.py::test_the_container_local_step_is_not_masked` | yes (`continue-on-error` present) | yes |
| `python3 tools/container_local_check.py` with `unshare` refused | `FAIL`, exit 1 | `UNSUPPORTED`, exit 2 |

---

## BUG-TL-0016 — The `publish` subcommand was unreachable dead code

| Field | Value |
|---|---|
| Severity | P1 |
| Component | `tools/docker_build_info.py` (`main`) |
| Status | VERIFIED FIXED |
| Discovered by | Phase 18 close-out: auditing what the CI provenance step actually executes |

### Symptom

In `tools/docker_build_info.py main()`, the `publish` branch was indented
*inside* the `verify` branch, **after** that branch's `return`:

```python
    if args.command == "verify":
        ...
        return 0 if result["status"] == "PASS" else 1

        if args.command == "publish":      # <- unreachable
            ...
```

`python3 tools/docker_build_info.py publish` therefore never reached its own
handler. It fell through to `result = resolve()` and then died on the next
line with an unhandled exception:

```
AttributeError: 'Namespace' object has no attribute 'report_status'
```

(exit code 1).

### Impact

The CI step named *"Publish the image build provenance (base digest, Python
patch version, package versions)"* has never published anything: it crashed.
The image's own provenance record was therefore never compared with the
committed `docs/EVIDENCE/docker-build-info.json` in CI, so the drift check
that was supposed to protect the pinned base image never ran. The crash was
invisible because the step ended in `|| true` (see BUG-TL-0017).

### Fix

The `publish` branch is now at the same level as the other subcommand
branches, so `publish` runs the publisher. The dead code, the misleading
step name and the `|| true` are gone.

### Regression evidence

| Test | Fails on old code | Passes on new code |
|---|---|---|
| `tests/judge/test_ci_masking.py::test_publish_calls_publish_and_not_resolve` | yes (`resolve` was called) | yes |
| `tests/judge/test_ci_masking.py::test_publish_does_not_raise` | yes (`AttributeError`) | yes |
| `python3 tools/docker_build_info.py publish --json` | `AttributeError`, exit 1 | `{"status": "UNAVAILABLE", ...}`, exit 0 |

---

## BUG-TL-0017 — The workflow masked exit statuses, and nothing prevented it

| Field | Value |
|---|---|
| Severity | P1 |
| Component | `.github/workflows/ci.yml`, `tools/check_workflows.py` |
| Status | VERIFIED FIXED |
| Discovered by | Phase 18 close-out: the audit of the masked failure (BUG-TL-0015, BUG-TL-0016) |

### Symptom

Two constructs in the workflow hid a non-zero exit status:

* `continue-on-error: true` on the container-equivalent step, and
* `|| true` on the provenance-publish step.

`tools/check_workflows.py` — the static guard that `make lint` runs over the
repository's own workflows — had no policy against either. It only checked
that the YAML parses.

### Impact

Any step that failed was reported as successful, and the static guard that
should have caught it had no rule to catch it with. This is the mechanism
that let BUG-TL-0015 and BUG-TL-0016 stay invisible for a whole release
cycle.

### Fix

* The workflow no longer masks anything: the publish step's `|| true` is
  removed (a genuine base-image/digest drift now fails the authoritative
  `docker-offline` job), and `continue-on-error` is gone.
* `tools/check_workflows.py` gained `scan_masking()` and a **masking policy**:
  `continue-on-error: true` and a `|| true` / `|| :` / `|| exit 0` tail on a
  command are refused, with the reason spelled out. `make lint` runs it over
  the repository's own workflows, so a regression cannot reach a push.

### Regression evidence

| Test | Fails on old code | Passes on new code |
|---|---|---|
| `tests/judge/test_ci_masking.py::test_continue_on_error_is_flagged` | yes (no rule existed) | yes |
| `tests/judge/test_ci_masking.py::test_a_masked_command_is_flagged` | yes (no rule existed) | yes |
| `tests/judge/test_ci_masking.py::test_the_repository_workflows_pass_the_policy` | yes (the old workflow masked two steps) | yes |
| `python3 tools/check_workflows.py` | PASS (the masked workflow passed) | PASS (the clean workflow passes; the masked one does not) |

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
| BUG-TL-0010 | P1 | `.dockerignore` (root-anchored rules leaked bytecode/secrets) | VERIFIED FIXED |
| BUG-TL-0011 | P1 | `Dockerfile` (floating base image tag) | VERIFIED FIXED |
| BUG-TL-0012 | P2 | `docker-compose.yml` (no process/file-size limits) | VERIFIED FIXED |
| BUG-TL-0013 | P2 | `judge/performance_and_deps.py` (substring check) | VERIFIED FIXED |
| BUG-TL-0014 | P2 | `tools/docker_build_info.py` (package-version drift check) | VERIFIED FIXED |
| BUG-TL-0015 | P1 | `tools/container_local_check.py` + `.github/workflows/ci.yml` (masked CI failure) | VERIFIED FIXED |
| BUG-TL-0016 | P1 | `tools/docker_build_info.py` (unreachable `publish` branch) | VERIFIED FIXED |
| BUG-TL-0017 | P1 | `.github/workflows/ci.yml` + `tools/check_workflows.py` (no masking policy) | VERIFIED FIXED |

No claim is made that no bugs remain. Checks that were executed without
finding a defect are listed in `FIX_VERIFICATION_MATRIX.md`, and residual
limitations are listed in `FINAL_QUALITY_REPORT.md`.
