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

## Summary

| ID | Severity | Component | Status |
|---|---|---|---|
| BUG-TL-0001 | P0 | `scoring/reward.py` | VERIFIED FIXED |
| BUG-TL-0002 | P0 | `env/cursors.py` | VERIFIED FIXED |
| BUG-TL-0003 | P1 | `env/cursors.py` | VERIFIED FIXED |
| BUG-TL-0004 | P1 | official C05 test | VERIFIED FIXED |

No claim is made that no bugs remain. Checks that were executed without
finding a defect are listed in `FIX_VERIFICATION_MATRIX.md`, and residual
limitations are listed in `FINAL_QUALITY_REPORT.md`.
