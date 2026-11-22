# Phase 15 — Structural Audit: Documentation That Numbers Cannot Save

- **Status:** `DONE` — `EXIT GATE 15: PASS` (re-established on stricter terms)
- **Date:** `2026-11-22`
- **Branch:** `arena/a30551a9-genesis-hackathon-malika-nurzh`
- **Base commit:** `e0a2bbf4bdf652f40855fc3c9a55fb3ccf64772a` (`main`, merge of PR #24)
- **Phase tasks:** 15.1 README/DESIGN/LIMITATIONS/DATA_DICTIONARY · 15.2 THREAT_MODEL/INDEPENDENCE · 15.3 API usage + policy protocol · 15.4 3-minute demo + technical backup · 15.5 claims link to artifacts · 15.6 no unsupported claims or fake metrics
- **Requirements:** `REQ-DOC-001`, `REQ-DOC-002`, `REQ-DOC-003`, `REQ-DEMO-001`, `REQ-JUDGE-001`, `REQ-JUDGE-005`
- **Decisions:** `D-15-04`, `D-15-05`, `D-15-06`

---

## 1. Why this audit exists

Phase 15 was reported `DONE` twice. The second report (2026-11-21) built a
genuinely good mechanism — `tools/verify_doc_claims.py` re-measures every
published **number** against the artifact that produced it, and 18 tests prove
the mechanism fires. That work is sound and is preserved unchanged.

But it verifies one axis only. Re-auditing against the literal EXIT GATE text —

> **"the jury can deploy the project from the README and verify the key claims"**

— found that the *numbers* were right while the *sentences around them* described
things that do not exist. A judge does not read a number in isolation; they read
"run `X`", open `Y`, and check the table that says what the demo does. Every one
of those failed.

**The gate was measuring the wrong axis, and doing it well.** Nineteen defects
were found by hand, all of them in the class "the documentation asserts a shape
that the repository does not have".

---

## 2. Defects found — all reproduced before fixing

### 2.1 The most serious: an independence claim the repository cannot evidence

`docs/INDEPENDENCE.md` opened with:

> Generator (Zone 1): Owner A. · Verifier (Zone 3): Owner C (**different human
> owner**, REQ-ORG-001).

`.github/CODEOWNERS` listed four GitHub handles (`@twinledger-owner-a..d`) that
do not exist. Master TZ §4 requires the verifier be built under a different human
owner or agent context from the generator. **This repository was produced by AI
agents in one shared session context.** The organisational half of the claim was
never true and was stated as fact.

This matters more than any other defect here: independence is the project's
central architectural argument, and the document asserting it overstated what was
proven. The *technical* half is real and now separated from it explicitly:

| Claim | Before | After |
|---|---|---|
| Different humans built generator and verifier | asserted | **explicitly retracted**; "not evidenced" |
| Verifier cannot import the generator | true, tested | stated with the exact evidence (`RC-002`, `tests/verifier/test_boundaries.py`) |
| Verifier never opens a sealed file | true, tested | stated with the runtime file-open spy evidence |
| No shared detection logic | true | unchanged, evidence cited |

`docs/QUESTIONS.md` gains `Q-ORG-01`/`Q-ORG-02` as **OPEN**, with the honest
answer written in: *unevidenced*. `AGENTS.md` and `.github/CODEOWNERS` now label
the zone table as *intended* ownership, not a record of review.

### 2.2 `docs/CONTEXT/ARCHITECTURE_SNAPSHOT.md` was a plan, not a description

Seven modules it named had never existed:

`contracts/money.py` · `contracts/rounding.py` · `contracts/time_utils.py` ·
`gen/diff.py` · `gen/distractors.py` · `gen/operators/` · `verifier/ablation.py`

It also published a test count of 295 and a gate range of `RC-001..RC-005`
(actual: 12 gates). The real tree has `core/money.py`, `gen/truth.py`,
`gen/distractors/catalog.py`, `gen/errors/operators.py`,
`verifier/minimal_sets.py`. Rewritten entirely as-built.

### 2.3 A workbench route that returned 404

`docs/API_USAGE.md` published `GET /api/episode/<split>/<id>/overview`. It was
never implemented. Verified live:

```
/api/health                                            -> 200
/api/episodes                                          -> 200
/api/episode/dev/ep_dev_001_clean_distractors/overview -> 404   <-- documented
/api/episode/dev/ep_dev_001_clean_distractors/verify   -> 200
```

Implemented rather than deleted, because the route is useful and returning only
public facts. Now serves metadata, manifest validity and table counts; still 404s
on an unknown episode and on `../` traversal (both re-tested).

### 2.4 `docs/DATA_DICTIONARY.md` described a data model that does not exist

Verified field-by-field against a real generated episode:

| Documented | Reality |
|---|---|
| `bank_lines.matched_payment_id` | not a field — matching is the auditor's inference |
| `bank_lines.bank_account_id` | not a field |
| — | `bank_lines.counterparty_text` exists (real bank-statement free text), undocumented |
| — | `fx_rates.fx_id` exists, undocumented |
| — | `invoices.recognition_rule` (1/30 rows), `invoices.subscription_period` (2/30), `payments.payment_type` (1/20), `payments.related_payment_id` (1/20) all real, all undocumented |

The four minority fields are the machine-readable half of the clean-distractor
catalogue — a recurring invoice is not a duplicate, a refund is not a duplicate
payment. Omitting them from the dictionary hid the mechanism that stops the
anomaly operators raising false positives. Rewritten and now compared in **both**
directions against `episodes/dev/ep_dev_001_clean_distractors`.

### 2.5 The demo documentation described a different demo

`docs/DEMO.md` said "five segments" and printed a table of five; the program
printed **six**, with a clock up to 5 seconds out of step (segment 1 documented
`0:00–0:30`, printed `0:00–0:25`; segment 2 `0:30–1:00` vs `0:25–0:55`).

### 2.6 Three documents called the reward "provisional" after it became official

`D-18-01` (2026-11-21) made the organisers' formula the single implementation and
explicitly recorded that `configs/scoring/default.json`'s `eta: 0.05,
provisional: true` **no longer influences the reward**. `docs/DESIGN.md`,
`docs/API_USAGE.md` and `docs/RELEASE_NOTES.md` still said otherwise — telling a
judge to discount a formula the organisers themselves fixed.

### 2.7 False measured values and one false command

| Location | Claim | Measured |
|---|---|---|
| `docs/LIMITATIONS.md` L7 | ≤292 rows per table | **146** |
| `docs/LIMITATIONS.md` L7 | ≤27 KiB per file | **26.9 KiB** (27 545 B, true but rounded up) |
| `docs/LIMITATIONS.md` L7 | ">500x/20x headroom" | **609x / 685x** |
| `docs/DESIGN.md` §6 | "12 gates, 21 artifacts" | 20 (`D-15-03`) |
| `docs/RELEASE_NOTES.md` | `python3.11 -m make verify` | **fails**: `No module named make` |
| `docs/RELEASE_NOTES.md` | 494 files / 5 449 805 bytes | 521 / 5 643 787 on this tree |

### 2.8 Phantom paths in two more documents

`docs/STATUS.md` cited `reward_property_matrix.json` (artifact is
`reward_property_matrix` inside the summary, not a standalone file);
`docs/OFFICIAL_COMPLIANCE_MATRIX.md` cited two test files without their
`tests/official/` prefix, so the reference did not resolve.

---

## 3. The fix: a second axis, with the same discipline

Numbers are re-measurable; sentences are not. So every sentence that asserts a
shape is now pinned to the thing that defines it. Six new detectors in
`tools/verify_doc_claims.py`, each with a negative test:

| Check | Pins | To what | Failure it catches |
|---|---|---|---|
| `C-PATHS` | every backticked repo path in 17 docs | the filesystem | documenting a file that does not exist |
| `C-DATADICT` | every field list in `DATA_DICTIONARY.md` | a real generated episode, **both directions** | phantom fields; silently omitted fields |
| `C-DEMO` | the `DEMO.md` segment table | `demo_walkthrough.py::SEGMENTS` | a narration of a demo that is not the one that runs |
| `C-WORKBENCH-API` | every documented HTTP route | `demo_server.py`'s real dispatchers | a documented route that 404s |
| `C-COMMANDS` | every `python3 x.py`, `-m pkg.mod`, `make t` | the filesystem and the Makefile | a command that cannot be run |
| `C-REWARD` | reward provenance | `scoring/official_scorer.py` constants | a doc contradicting `D-18-01` |

Three design rules were forced by the work itself:

1. **`SEGMENTS` is the single source.** `tools/demo_walkthrough.py` now owns a
   `SEGMENTS` tuple; the program prints its headers from it and `C-DEMO` compares
   `docs/DEMO.md` against the same tuple. Two copies of a clock is one copy too
   many.
2. **Generated artifacts are asserted by contract, not by presence.** A bare
   `replay_report.json` is legitimate prose on a bare checkout. It is resolved
   against `judge/verify.py::REQUIRED_FULL_ARTIFACTS` — the gate's own frozen
   list — so the check is meaningful before any artifact exists.
3. **Absence must be documentable.** "`gen/diff.py` does not exist" is a true
   sentence; a naive path check fails it. Lines carrying a negation cue
   (`does not exist`, `forbidden`, `renamed`) are exempt.

### 3.1 A hole in the new detector, found by its own negative test

Injecting `accounts.bogus_field` into the dictionary **passed**. Cause: `accounts`
was not in the comparison list, and the loop `continue`d on any table it could not
resolve. A documented table that cannot be verified is worse than a failing one —
it looks green.

Fixed twice: all ten tables are now compared, and an unresolvable documented
table raises `UNRESOLVED_TABLE` instead of being skipped. Regression test
`test_every_documented_table_is_actually_compared` asserts the list stays complete.

### 3.2 The gate caught its own author

Adding 22 tests to `tests/judge/test_doc_claims.py` changed the measured count
from 502 to 522, and the next `make verify` failed with:

```
[DRIFT] G-BLOCK: line 11: committed '502' != measured '522'
```

That is the mechanism working exactly as designed. Rather than re-type the number,
the redundant hand-written prose copy was removed: the test count is now published
**once**, in the generated block. A count that appears twice is a count that will
eventually disagree with itself.

---

## 4. Commands run in this session

| Command | Exit | Result |
|---|---:|---|
| `make verify` (baseline, before changes) | 0 | 12/12 PASS, 47.2 s, 20 artifacts |
| `make verify` (after changes, empty evidence dir) | 0 | **12/12 PASS**, 51.0 s, 20 artifacts, docs gate PASS |
| `make lint` | 0 | `import boundary scan: CLEAN (REQ-ARC-001..007)` |
| `python3 tools/freeze_release.py --verify` | 0 | **30 frozen files intact**, `0747baf0…` — no contract touched |
| `python3 -m unittest tests.judge.test_doc_claims` | 0 | **47 tests OK** (was 25) |
| `python3 tools/verify_doc_claims.py` | 0 | **PASS, 22 measured facts, 17/17 checks** (was 11) |
| `python3 tools/verify_doc_claims.py --write` | 0 | facts block regenerated (522 tests) |
| `python3 tools/demo_walkthrough.py` | 0 | 6 segments, all four reward stress rows, `full_os_sandbox=True` |
| `python3 tools/demo_server.py` + 4 live route probes | 0 | `/overview` 200 with public data; unknown episode 404; `../` 404 |

### 4.1 Negative tests — every detector shown to fail

| Injected fault | Observed |
|---|---|
| `verifier/nonexistent_detector.py` cited in `DESIGN.md` | `[MISSING_PATH] C-PATHS`, exit 1 |
| one demo clock reverted to `0:00–0:30` | `[CLOCK_MISMATCH] C-DEMO`, exit 1 |
| `accounts.bogus_field` added to the dictionary | `[PHANTOM_FIELD] C-DATADICT`, exit 1 |
| "reward parameters are provisional" re-added | `[STALE_PROVISIONAL] C-REWARD`, exit 1 + `[GOVERNING_CONFIG_CLAIM]` |
| `` `make fake-target` `` added to `DEMO.md` | `[PHANTOM_TARGET] C-COMMANDS`, exit 1 |
| documented `/overview` route (pre-fix, live) | HTTP **404** |

---

## 5. Files

**Tooling:** `tools/verify_doc_claims.py` (six structural detectors, contract-derived
artifact resolution, negation exemption, unresolved-table failure).
**Program:** `tools/demo_walkthrough.py` (`SEGMENTS` tuple, `_segment()` renderer,
distractor count read from the manifest), `tools/demo_server.py` (`/overview`).
**Tests:** `tests/judge/test_doc_claims.py` (+22 tests, 25 → 47).
**Docs rewritten:** `docs/CONTEXT/ARCHITECTURE_SNAPSHOT.md` (as-built),
`docs/DATA_DICTIONARY.md` (both-direction verified), `docs/INDEPENDENCE.md`
(honest ownership correction).
**Docs corrected:** `docs/DEMO.md` (segment table + count), `docs/DESIGN.md`,
`docs/API_USAGE.md`, `docs/LIMITATIONS.md` (L7 numbers), `docs/RELEASE_NOTES.md`
(command + file/byte counts + reward status), `docs/STATUS.md`,
`docs/OFFICIAL_COMPLIANCE_MATRIX.md`, `docs/QUESTIONS.md` (4 OPEN process
questions), `README.md` (documentation index; generated block refreshed),
`AGENTS.md`, `.github/CODEOWNERS`.

**Frozen files changed: none.** `contracts/*`, `configs/*`,
`judge/rubric_map.json` and the Master TZ are untouched; freeze verify PASS
(30 files, `0747baf0…`). No `docs/reference/` change.

---

## 6. Deviations and limitations

1. **The organisational independence gap is disclosed, not fixed.** Only a human
   owner can close `Q-ORG-01` — either by re-deriving the verifier under a
   separate context or by accepting and disclosing the gap. This report chooses
   disclosure.
2. **`C-PATHS` is a presence check, not a correctness check.** A doc can cite a
   real file and still misdescribe it; `C-DATADICT`, `C-DEMO` and
   `C-WORKBENCH-API` close that for the three shapes where it mattered most, but
   prose describing *behaviour* is still only partly mechanical.
3. **`C-COMMANDS` proves resolvability, not success.** Running every documented
   command is `make demo-backup`'s job (`B1..B4`), which remains the authoritative
   check.
4. **`C-REWARD` scans paragraphs, not semantics.** A paragraph that mentions
   `configs/scoring/default.json` and `provisional` without a denial cue fails;
   the converse (correct prose phrased without any of the six cues) would also
   fail, and the fix would be to reword, not to weaken the check.
5. **`docs/STATUS.md` and `docs/PHASE_REPORTS/*` keep their historical numbers.**
   A status page is a dated record; rewriting it would destroy the audit trail.
   They are covered by the structural checks, not by the numeric ones.

---

## 7. Next-phase readiness

EXIT GATE 15 is satisfied on the stricter reading: a judge can now follow the
README, open the files it names, call the routes it documents, run the commands it
prints, and compare the demo they watch against the demo the document describes —
and every one of those is a machine check that fails loudly.

Open items passed forward, none blocking:

1. `Q-ORG-01` — organisational independence (needs a human owner).
2. `Q-REL-01` — should `v1.0.1` be cut? `v1.0.0` still carries the
   `.dockerignore` defect from `D-16-02`.
3. `docs/STATUS.md` needs a row for this audit (added).

**Sign-off:** Phase 15 structural audit complete. 19 defects found by hand, 6 new
detectors added, each proven to fire, each locked by a test. `make verify` 12/12
PASS from an empty evidence directory, docs gate PASS 17/17, frozen surface
untouched.
