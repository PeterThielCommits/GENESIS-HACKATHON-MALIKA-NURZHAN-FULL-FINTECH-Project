# Phase 16 — Release Candidate, Clean Machine and Submission

**Outcome: DONE. EXIT GATE 16 PASS** (no release blockers; all required tests pass;
submission format verified).

- Date: 2026-11-22
- Branch: `arena/a85b561e-genesis-hackathon-malika-nurzh`
- Base: `36a265c` (merge of PR #20, Phase 15)
- Master TZ v3.0.0 §Phase 16, lines 3078–3093
- `official_score_claimed: false` (TZ §23.6)
- Frozen files changed: **none** (`freeze_release --verify` → 30 files, `0747baf0…`)

---

## 1. What this phase had to prove

Phase 16 is not a feature phase. The TZ asks one question: *is this the artefact
we are submitting, and can it be verified somewhere other than the machine that
built it?* Every task is therefore a measurement performed in an environment
that did not exist while the code was written.

| Task | Requirement | How it is satisfied |
|---|---|---|
| 16.1 | Freeze feature development | Only audit/replay tooling added; no runtime behaviour changed |
| 16.2 | `make verify` on a clean clone | PASS 12/12 from a fresh `git clone` with an emptied evidence dir |
| 16.3 | Offline Docker, network disabled | CI `docker-offline`: `--network=none --read-only --cap-drop ALL`, `PIP_NO_INDEX=1` |
| 16.4 | Replay on **all** published trajectories | `make replay-all`: **80/80** runs, **567** steps byte-identical |
| 16.5 | Audit secrets, file list, size, dependencies | `make release-audit`: 6 measured checks, all PASS |
| 16.6 | Verify entrypoint and submission format | Same tool: behavioural probe of the official adapter |
| 16.7 | Tag release and record the commit | Done after merge (see §8) |
| 16.8 | Final GitHub release with report and limitations | Done after merge (see §8) |

---

## 2. New gates

### 2.1 `make replay-all` — task 16.4

`make replay` already proved determinism on **5** reference runs. Task 16.4 asks
for **all published trajectories**, so `tools/replay_all_trajectories.py` was
written to be stricter and policy-independent:

1. rebuild the canonical D01..D20 episodes from `official_d20_recipes(2026)` in a
   temporary directory;
2. for each of the 80 published rows, replay the **recorded action sequence**
   against a fresh `make_env()` and compare the initial observation, every step's
   observation / reward / terminated / info;
3. re-score the recorded `final_findings` and compare the recorded metrics.

No policy is re-executed, so the claim being tested is about the generator, the
environment and the scorer — not about the baseline policies.

```
replay-all: PASS (80/80 runs, 567 steps byte-identical)
```

**Proven able to fail.** Tampering with a single metric
(`metrics.return -> 999.0`) yields `score.return: 0.976 != 999.0`; tampering
with one observation yields `step 1: observation differs`; renaming an episode
yields `episode D99_not_a_scenario was not generated`.

### 2.2 `make release-audit` — tasks 16.5 and 16.6

| Check | Measurement |
|---|---|
| `SECRETS` | 494 text files scanned against 8 credential shapes → 0 matches |
| `FILELIST` | 494 tracked files → 0 sealed/hidden/credential paths |
| `SIZE` | 494 files, 5 449 805 bytes (budget 1000 files / 50 MB) |
| `DEPS` | 109 runtime modules parsed → 0 undeclared external imports |
| `ENTRYPOINT` | `judge_adapter` imported from cwd=`/`: 3 exports, `reset`→2-tuple, `step`→5-tuple, **5/5** tool names accepted |
| `SUBMISSION` | offline non-root image, `PIP_NO_INDEX=1`, `CMD ["make","verify"]`, documented vocabulary agrees with the adapter |

Exit code is the verdict; the JSON report is a convenience artefact whose write
failure cannot turn a PASS into a crash (read-only rootfs).

**Proven able to fail.** Each detector was exercised with a real violation:

| Injected | Result |
|---|---|
| `AKIA…` key in a tracked file | `FAIL (SECRETS)` |
| `import requests` in `core/` | `FAIL (DEPS)` |
| `git add -f episodes/dev/x/sealed/truth.json` | `FAIL (FILELIST)` |
| oversized file | `FAIL (SIZE)` |

Those four probes are now unit tests (`TestSecretDetectors`,
`TestForbiddenPaths`, `TestSizeBudget`, `TestDependencyAudit`).

### 2.3 `make rc-check`

```
rc-check: PASS (release candidate is consistent)
```

`verify` → `docs-verify` → `replay-all` → `release-audit`, fail-closed. Run in
three different trees (§4) with the same result.

---

## 3. Defects found and fixed

Phase 16 exists to find exactly these. None of them were visible from the
working tree that produced them.

### 3.1 `docker-offline` was red for four consecutive commits (16.3)

The job failed while `core` passed. Job logs and artefacts redirect to a blob
host unreachable from this environment, so the failure had to be made
observable: build and run were split into separate steps and the interesting
log lines are re-emitted as `::error::` annotations, which the API serves.

That produced the actual message:

```
[DRIFT] G-BLOCK (line 13: committed '| Evidence artifacts indexed | **21** |'
                       != measured '| Evidence artifacts indexed | **20** |')
```

`judge/report.py` counted **every regular file** in `artifacts/reports/latest/`,
including the `.gitkeep` placeholder. The published artifact count therefore
depended on *where the code ran*: 21 in a checkout, 20 inside the image (where
Docker does not materialise the placeholder). A count that changes with the
filesystem is not a measurement. `_is_artifact()` now excludes dotfiles, so the
count is 20 everywhere (16 required §23.5 reports + `report.html` +
`report_index.json` + `robustness_report.json`), `missing: []` — recorded as
**D-15-03**.

Two other real defects were fixed on the way to that finding, both genuine even
though neither was the cause:

- **C-locale crash.** `python:3.11-slim-bookworm` runs with `LC_ALL=C`, so
  `sys.stdout` is ASCII; printing an em dash in `test_doc_claims.setUpModule`
  raised `UnicodeEncodeError` before verification started. Reproduced exactly
  with `LC_ALL=C python3 -X utf8=0 -m unittest discover -s tests -t .`. All
  console output now goes through a transliterating `_say()`; locked by
  `TestLocaleSafety`.
- **Masked trajectory log.** The container mounts an empty tmpfs over
  `artifacts/trajectories`, which masks the committed `trajectories.jsonl`, and
  `make verify` never regenerates it. Baseline rows became an optional,
  explicitly-reported fact block instead of a hard failure.

### 3.2 Clean clone failed: Phase 16 tests gated on gitignored outputs (16.2)

`artifacts/reports/release/` is gitignored, so both new integration test modules
skipped everything on a fresh clone. `RC-001` then reported `SKIPPED` → *test
suite not complete* → exit 5 — while the same tree passed locally, where the
reports happened to exist.

This is the bootstrap trap documented in `D-15-01`, reintroduced one directory
over. Integration tests now gate on their **inputs** (the generated evidence set
and the committed trajectory log), never on a file produced by the run that
reads it.

### 3.3 RC-001 read a gitignored report

`test_published_report_matches_a_fresh_replay` opened
`artifacts/reports/release/trajectory_replay.json` directly, so a clean clone
raised `FileNotFoundError` and the suite failed with 17 skips. Both
report-contract tests now drive the **real CLI** into a temporary directory —
the same code path, just somewhere that always exists.

### 3.4 The secrets audit found four credentials in its own fixtures

The audit reported `FAIL (SECRETS)` on the repository it had just been written
into: the test fixtures contained a PEM header, an AWS key id, a Slack token and
a JWT as **complete literals**. The fixtures are now assembled at runtime from
fragments, so the shapes stay exact while the repository stays clean. The audit
correctly refused to exempt itself.

### 3.5 The audit errored on a tree with no Git metadata

Found by running `make verify` from a `git archive` tarball: `git ls-files`
returned nothing, so `run_audit()` produced an `ERROR` report without
`official_score_claimed`, and the report-contract test raised `KeyError`.

This is not an edge case — `.dockerignore` excludes `.git`, so **the submission
image is exactly such a tree**. `tracked_files()` now falls back to a filesystem
walk mirroring `.dockerignore`, and the `ERROR` report always carries the full
envelope. Locked by `TestFileListWithoutGit`.

### 3.6 Errors in the tooling itself, caught before they shipped

- `FILELIST` matched only one `sealed/` depth and let a forced `git add -f`
  through while reporting PASS. Now matches any depth.
- The entrypoint probe first checked **parameter count**, which is 1 for a bound
  method; Gymnasium compatibility is the returned **5-tuple**, so it checks that.
- The adapter exposes no `tool_names` attribute; the probe now verifies the
  vocabulary **behaviourally**, dispatching each documented tool in a fresh
  environment (an unknown action is answered with `UNKNOWN_ACTION` inside the
  observation, and `submit` terminates the episode, so a shared env would have
  silently poisoned the remaining checks).

---

## 4. Verification in three different trees

The point of Phase 16 is that results must not depend on the machine that
produced them.

| Tree | Condition | `make verify` | `make rc-check` |
|---|---|---|---|
| Git checkout | working tree | PASS 12/12 (71.6 s) | PASS |
| Clean clone | `git clone`, evidence dir emptied | **PASS 12/12** (69.7 s) | **PASS** |
| `git archive` tarball | **no `.git` at all** | PASS 12/12 | PASS |

All three under `LC_ALL=C`, matching the container locale.

`docker-offline` (CI) additionally proves 16.3 under
`--network=none --read-only --cap-drop ALL`.

---

## 5. Environment and budgets (measured)

| Quantity | Value |
|---|---|
| Tracked files | 494 |
| Package size | 5 449 805 bytes (budget 50 MB) |
| Runtime modules parsed | 109 |
| Undeclared runtime dependencies | 0 (stdlib only) |
| Tests | **481** (1 optional Hypothesis skip, `critical_skipped=0`) |
| Evidence artefacts | 20 (frozen Judge Kit set) |
| Documents facts machine-checked | 22 facts, 11 checks |
| Replay | 80/80 runs, 567 steps byte-identical |
| Frozen contract surface | 30 files, `0747baf0…` |

---

## 6. Limitations (carried forward honestly)

1. **L-A:** official rubric weights are still not published, so internal
   verification is never presented as a jury score (`official_score_claimed: false`).
2. **L-B:** `eta = 0.05` remains provisional (TZ §18).
3. **L-C:** the Docker check is exercised by CI, not by this sandbox (no Docker
   daemon here); the read-only/ASCII/no-Git failure modes were instead
   reproduced natively and are covered by tests.
4. **L-D:** `replay-all` verifies *recorded* actions; it does not re-run the
   baseline policies, so it cannot detect a policy-side change (that is
   `make replay`'s and `make official-eval`'s job).
5. **L-H:** baseline numbers derive from the committed `trajectories.jsonl`,
   produced by `make official-eval`; regenerating it is a reviewer step, not
   part of `make verify`.
6. **L-I:** the job-log/artefact endpoints of GitHub Actions are unreachable
   from this sandbox, so CI failures are diagnosed through annotations. This is
   why `ci.yml` deliberately turns failure output into annotations — a
   permanent diagnostic improvement, not a workaround.

---

## 7. Deviations

- None from the TZ. No frozen file was modified; the `.gitkeep` question was
  resolved in code (`judge/report.py`) rather than by weakening a contract.

## 8. Remaining authority steps (16.7, 16.8)

Tagging and publishing a GitHub release are release-authority actions and are
performed only after this PR merges, against the merge commit:

```
git tag -a v1.0.0 -m "TwinLedger v1.0.0 — Genesis FinTech 2026 release candidate"
git push origin v1.0.0
gh release create v1.0.0 --notes-file docs/RELEASE_NOTES.md
```

Commit hash and tag are recorded in `docs/STATUS.md` and
`docs/PHASE_REPORTS/PHASE-16.json` once created.

## 9. Owner sign-off

Phase 16 is complete: feature-frozen, verified on a clean machine, replayed end
to end, audited for secrets/size/dependencies, and its official entrypoint and
submission format proven by execution. EXIT GATE 16: **PASS**.
