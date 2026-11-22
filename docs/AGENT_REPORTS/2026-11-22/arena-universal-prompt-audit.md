# Mandatory-target audit against the Universal Phase Execution Prompt

- Date: 2026-11-22
- Branch: `arena/c7683bf7-genesis-hackathon-malika-nurzh`, base `ff471ae` (merge of PR #22)
- Scope: **Phases 0–16 quality audit**, no new features. Phase 17 explicitly not started.
- Trigger: user asked whether the whole Universal Phase Execution Prompt had been
  executed. Honest answer: **no** — the prompt requires every mandatory command to
  be *actually run and recorded*; nine TZ §23.2 targets had never been executed,
  only assumed to work.

## 1. Method

The prompt's §3.3 asks for every phase item to be classified
`ALREADY VERIFIED / IMPLEMENTED BUT UNVERIFIED / MISSING / FAILING / BLOCKED`.
Applied to the command surface instead of the prose:

1. List every target in TZ §23.2 (14 required targets).
2. Check it exists in `Makefile` → all 14 did.
3. Check whether it appears in any phase report's `commands` table → **9 did not**.
4. Run every target for real, in sequence, on a tree dirtied by prior targets
   (a reviewer's tree, not a pristine checkout).
5. Run `make clean` and the full suite afterwards, to test order-independence.

Step 4 is the one that mattered. Every defect below was found there.

## 2. Defects found and fixed

### 2.1 `make verify-core` FAILED after `make build-episodes`

```
[FAIL] RC-001 (REQ-CONTRACT-001) ... : ['FILELIST'] | Ran 481 tests | FAILED
```

`tools/release_audit.py`'s filesystem fallback (added because the Docker image
has no `git`) scanned **untracked** files. `make build-episodes` legitimately
creates `episodes/*/*/sealed/truth.json`; sealed truth is gitignored *by design*
(deterministic distribution, never committed), so the walk reported **20 false
FILELIST violations**.

Fixed: `_is_ignored()` makes the walk honour the project's ignore rules, so it
now yields `git ls-files` minus the two intentionally-excluded generated paths.
`make verify-core` is PASS.

### 2.2 The Docker image would have shipped sealed truth — a release blocker

`.dockerignore` contained `episodes/*/sealed/`. Docker matches patterns per path
element, so that does **not** match the real depth-2 layout:

| Pattern | Matches `episodes/dev/ep_x/sealed/truth.json`? |
|---|---|
| `episodes/*/sealed/` (old) | **No** |
| `episodes/*/*/sealed/` (new) | Yes |

A default `make docker-check` would have baked `truth.json` into the submission
image, violating `REQ-ARENA-005`. Both depths are now listed. Proven by
`TestDockerIgnore`, which emulates per-element matching and fails on the old
pattern.

### 2.3 `make official-eval` broke the documented artifact count

It wrote `official_eval_summary.json` into `artifacts/reports/latest/`, turning
the frozen 20-file evidence set into 21 and making the README's "20 evidence
artifacts" false after a legitimate command. Relocated to
`artifacts/reports/evaluation/`. Proven by `TestEvidenceDirStaysFrozen`
(3 tests, including an exact count of 20).

### 2.4 The published gate count was a measurement, not the contract

After `make verify-core` the README's generated block said **6 gates** (the
number that ran) and the next full run reported `DRIFT` — an order-dependent
fact, the error class `D-15-01` forbids. The count now comes from the frozen
`judge/rubric_map.json` (12 gates), which is the contract.

## 3. Full sweep result

All 19 targets, one sequence, dirty tree, `LC_ALL=C`:

| Command | Exit | Status |
|---|---|---|
| `make help` | 0 | PASS |
| `make setup` | 0 | PASS (Python 3.11.2; pytest/hypothesis/jsonschema absent, optional) |
| `make lint` | 0 | PASS (REQ-ARC-001..007 CLEAN) |
| `make test-property` | 0 | PASS — 17 tests (1 optional Hypothesis skip) |
| `make build-episodes` | 0 | PASS — 10/10 episodes verified, `release_blocked=False` |
| `make verify-core` | 0 | PASS — 6/6 gates |
| `make replay` | 0 | PASS — 5/5 byte-identical, Merkle `d949fae3…`; P01..P20 matrix (1 test, 20 iterations) |
| `make audit-shortcuts` | 0 | PASS — AUC 0.5389, canary 0 hits (3 tokens, 10 channels, 9 encodings, 17 variant patterns), api_fuzz 10/10, C20 ok |
| `make mutation-test` | 0 | PASS — 26/26 mutants killed; Block 3 32 tests |
| `make test-official` | 0 | PASS — 55 tests |
| `make report` | 0 | PASS — offline HTML + index |
| `make official-eval` | 0 | PASS — 4 policies × D01..D20 |
| `make test` | 0 | PASS — full suite |
| `make docs-verify` | 0 | PASS — 22 facts, 11 checks |
| `make demo` | 0 | PASS — 5 segments, seed 2025 |
| `make demo-backup` | 0 | PASS — verify + docs + replay 5/5 + freeze 30 |
| `make replay-all` | 0 | PASS — 80/80 runs, 567 steps |
| `make release-audit` | 0 | PASS — 6/6 checks |
| `make rc-check` | 0 | PASS |
| `make clean` | 0 | PASS |

**19/19 exit 0, 0 failures.** This is the first time that has been demonstrated;
previous phases verified a subset and inferred the rest.

## 4. Determinism across the sweep

`make official-eval` rewrites the committed `trajectories.jsonl`. Compared
against `HEAD` row by row:

- 80 rows before, 80 after
- differing keys: **`duration_s` only**
- every observation, reward, metric, finding and step count identical

`make replay-all` still PASSes on the restored log (80/80, 567 steps). Wall-clock
is deliberately excluded from determinism claims (`D-15-01`), so the log was
restored rather than committed.

## 5. Gaps closed / remaining

| Gap | State |
|---|---|
| `CONTRIBUTING.md` missing (prompt §3.2 lists it) | **created** |
| 9 mandatory targets never executed | **now executed, all PASS** |
| Exit codes 2/3/4/5 | covered by unit tests on `classify_check` (pre-existing) |
| `make clean` then `make test` | 481 tests, 17 explicit skips (correct bootstrap) |
| Docker daemon in this sandbox | **not available** — `docker-check` is exercised by CI (`docker-offline` job, green); read-only/ASCII/no-git failure modes reproduced natively |
| Phase 17 | **not started** (user instruction) |

## 6. Verdict

Phases 0–16 are **VERIFIED against the real EXIT GATES**, not assumed. Four real
defects were found by executing commands that were previously only believed to
work, one of them a release blocker (sealed truth in the image). Recorded as
`D-16-02`.

Phase 16 remains released as `v1.0.0` on `8da0af2`. The fixes here are
post-release hardening and are **not** in the released tag; whether to cut a
`v1.0.1` is a release-authority decision, not an engineering one.
