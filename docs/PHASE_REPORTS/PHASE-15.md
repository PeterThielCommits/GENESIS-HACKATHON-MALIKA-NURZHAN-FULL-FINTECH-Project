# Phase 15 Report — DOCUMENTATION & DEMO (re-audit)

- **Status:** `DONE` — `EXIT GATE 15: PASS`
- **Date:** `2026-11-21`
- **Branch:** `arena/41a4694b-genesis-hackathon-malika-nurzh`, base `ff6e470` (`main`)
- **Phase tasks:** 15.1 README/DESIGN/LIMITATIONS/DATA_DICTIONARY · 15.2 THREAT_MODEL/INDEPENDENCE · 15.3 API usage + policy protocol · 15.4 3-minute demo + technical backup · 15.5 claims link to artifacts · 15.6 no unsupported claims or fake metrics
- **Requirements:** `REQ-DOC-001`, `REQ-DOC-002`, `REQ-DOC-003`, `REQ-DEMO-001`, `REQ-JUDGE-001`, `REQ-JUDGE-005`
- **Decisions:** `D-15-01`, `D-15-02`

## 1. What EXIT GATE 15 actually requires

> **EXIT GATE 15:** the jury can deploy the project from the README and verify the key claims.

The earlier Phase 15 report claimed DONE with "complete, honest documentation". Re-auditing against that sentence found the documentation was *descriptive but not checkable*, and in two places actively wrong.

## 2. Defects and gaps found

### 2.1 Task 15.3 had no deliverable at all
No `API_USAGE.md` and no policy-protocol document existed. The README carried a partial adapter description, but the JSONL wire contract — envelopes, tool enum, error enum, budgets, limits — existed only in code and in the Master TZ. **Added:** `docs/API_USAGE.md`, `docs/POLICY_PROTOCOL.md`.

### 2.2 A real tool-name trap was undocumented
The core protocol accepts `calc`; the official adapter accepts `calculator`. Each rejects the other's name. A judge writing a policy from the README's adapter table and then running it against `env/jsonl_server.py` would get an immediate failure with no explanation. Verified empirically both ways:

```
adapter  tool='calculator' -> 0.3        | tool='calc' -> UNKNOWN_ACTION
jsonl    tool='calc'       -> ok=True    | tool='calculator' -> UNKNOWN_TOOL
```

Now documented explicitly in both files (README note + `POLICY_PROTOCOL.md` §3 vocabulary table), and pinned by an automated check (`C-PROTOCOL-TOOLS`).

### 2.3 A claim that was simply wrong
`docs/THREAT_MODEL.md` listed "9 encoding transforms" followed by **8** names, four of which were not the real transform identifiers. The actual transform list in `judge/canary_fuzzer.py` is `exact_utf8, casefold, hex_lower, hex_upper, base64_standard, base64_urlsafe_nopad, url_percent_encoded, unicode_nfc, unicode_nfkc`. Corrected and now source-driven.

### 2.4 Stale numbers
`README.md` published **317 tests** (measured: **410**, now 477 after the new Phase 15 tests) and `mutation_score_exact: "26/26"` quoted as a percentage field. The baseline table's max-duration column did not match `trajectories.jsonl` (`0.004s` vs `0.005s`, `7.3` vs `7.35` steps).

### 2.5 A phantom decision ID (my own error, caught by the new check)
While rewriting `DESIGN.md` I cited `D-03-01`, which does not exist in `docs/DECISIONS.md`. Rather than just fix the prose, this is now a **referential-integrity check**: every `D-XX-YY` cited anywhere in the docs must be defined in `DECISIONS.md`, or the gate fails.

### 2.6 `DESIGN.md` and `DATA_DICTIONARY.md` described a plan, not the system
`DESIGN.md` still said "planned, Phase 9 / Phase 6" for shipped components. Rewritten as an as-built design; the phase-plan text is preserved in `docs/PHASE_REPORTS/`.

## 3. The core of this phase: claims are now machine-checked

Task 15.6 ("no unsupported claims or fake metrics") cannot be satisfied by care alone — it decays on the next edit. New tool `tools/verify_doc_claims.py` enforces it with **four mechanisms**:

| Mechanism | What it stops |
|---|---|
| **Generated facts block** in `README.md` (`<!-- BEGIN GENERATED:measured-facts -->`) rendered from artifacts and compared byte-for-byte | any hand-edited number silently drifting |
| **Prose assertions** (`477 tests`, `12-gate Judge Kit`, `5/5 byte-identical replays`, protocol enums) | stale counts in running text |
| **Stale-literal denylist** across 10 docs (`317 tests`, `Replay Suite: 0/0`, `15 invariants`, …) | old wrong values being reintroduced |
| **Decision-ID referential integrity** | phantom `D-XX-YY` citations |

All four were **proven to fire** with deliberate-corruption tests, and are locked by `tests/judge/test_doc_claims.py` (18 tests). The mechanism tests run inside RC-001; the authoritative check runs in `judge/verify.py` after artifacts exist (§3.1).

### 3.1 Three ordering bugs the clean-checkout run exposed

The gate was first placed inside the RC-001 test suite. A clean-checkout run (the standard Phase 14 established) proved that placement **cannot** work:

1. **Chicken-and-egg.** The doc-claim tests read `verify_summary.json`, which is written by the very run executing them — so on a clean tree they crashed with `FileNotFoundError` and RC-001 failed. Fixed: the tests now skip explicitly in that bootstrap position (`evidence artifacts not generated yet`), and are treated as an *optional* positional skip by the classifier.
2. **Authoritative check relocated.** `judge/verify.py` now runs `tools/verify_doc_claims.py` **after** every artifact exists (`_run_doc_claims()`), which is the only ordering in which the check can be meaningful. A failure there counts as a failed required gate; an absent checker makes the suite *incomplete*, never passing.
3. **Circular self-reference.** Publishing the gate pass-ratio ("12/12 PASS") as an asserted fact was self-poisoning: a run that failed *because of doc drift* wrote a failing summary, which changed the expected wording for the next run — an unrecoverable deadlock. Fixed by asserting only **outcome-independent** facts (e.g. "12-gate Judge Kit", counts, contract enums); the verdict is carried by the exit code and `verify_summary.json`.

A fourth bug was caught by the tests themselves: one test hardcoded `**12/12**` as the value to corrupt, so it silently stopped testing anything once that fact was removed. It now derives the value from the rendered block.

### 3.2 The hardened offline container rejected the new directory (CI catch)

The `docker-offline` CI job runs `make verify` with `--read-only` rootfs and tmpfs mounts only for `artifacts/reports/latest` and `artifacts/trajectories`. The new Phase 15 report directory was therefore unwritable, and an unwritable path raised `FileNotFoundError` instead of reporting the verdict. Two fixes, both correct in their own right:

1. `Dockerfile` pre-creates `artifacts/reports/doc_claims`, and `make docker-check` mounts a 16 MB tmpfs there — the rootfs stays read-only.
2. `tools/verify_doc_claims.py` now treats the report as a convenience artifact, never as the verdict: if the write fails it prints a note and returns the real exit code.

#### Third run: the actual docker-only cause was the locale

Two fixes in, `docker-offline` still failed while `core` kept passing. The
difference that only exists inside the container is the **locale**: `python:3.11-slim-bookworm`
runs with `LC_ALL=C`, so `sys.stdout.encoding` is ASCII. Any printed em dash,
arrow or section sign then raises `UnicodeEncodeError`. Reproducing it
(`LC_ALL=C python3 -X utf8=0 -m unittest discover -s tests -t .`) failed
immediately in `test_doc_claims.setUpModule` on the string `artifacts present —`.

Fixed properly rather than by deleting punctuation:

- `tools/verify_doc_claims.py` has a single output path, `_say()`, which
  transliterates non-ASCII to ASCII before printing; `--json` uses
  `ensure_ascii=True`. Files are still written as explicit UTF-8.
- `tests/judge/test_doc_claims.py` prints ASCII only.
- `TestLocaleSafety` (3 tests) locks the contract and asserts no raw
  `print()` in `main()` bypasses it.

Whole suite under `LC_ALL=C`/ASCII: **477 tests, OK**. Full simulated container
layout under `LC_ALL=C` + empty trajectories + read-only evidence dir:
`make verify` 12/12 PASS.

#### Second run: the masking problem underneath it the job still failed. The deeper cause is that `make docker-check` mounts an **empty tmpfs over `artifacts/trajectories`**, which *masks* the committed `trajectories.jsonl`. Nothing in `make verify` regenerates that file (it comes from `make official-eval` and is committed), so the baseline rows — an asserted fact — were unreadable and the drift check fired. The masking is deliberate and correct: an offline container should prove it produces its own outputs from scratch.

Fixed by making baseline rows an **optional fact block**: `baseline_log_available()` probes the log; when it is absent the block says so explicitly (`_(baselines omitted)_` + the reason), the comparison skips that section, and `--write` never erases the published rows. Verified in three ways: real repo (PASS), log removed (PASS), and a full simulated container layout with an empty trajectories directory (`make verify` 12/12 PASS). Locked by `TestOfflineContainerTolerance` (4 tests).

### 3.3 Pre-existing tooling gap this exposed

`make verify` writes `artifacts/trajectories/trajectories.jsonl` only via `make official-eval`, so the documentation checks depend on a checked-in file. That is deliberate (the trajectory log is a committed reproducibility artifact), but it means the doc gate measures a file that `make verify` does not regenerate. Recorded as limitation L-H below.

### 3.4 Determinism of the gate itself (a design bug found and fixed)

First implementation put *sampled* metrics (p99 latency, peak RSS, max episode time) into the byte-compared block. Those vary per run, so the gate failed on the very next `make verify` — a self-defeating check. Fixed by publishing only **stable** facts (budgets, verdicts, counts, contract enums) and excluding wall-clock timings from the generated table. Verified by running `make verify` twice in a row and re-checking: PASS both times.

The relocated report also avoids a subtler trap: `artifacts/reports/latest/` is the frozen 21-artifact Judge Kit evidence set, so writing the doc-claims report there would have made the artifact count depend on whether `make docs-verify` ran before or after `make verify`. It lives in `artifacts/reports/doc_claims/` instead.

## 4. Task 15.4 — two demos, not one

| | Primary | Technical backup |
|---|---|---|
| Command | `make demo` / `python3 tools/demo_walkthrough.py` | `make demo-backup` |
| Proves | product story (5 segments, seed 2025) | reproducibility & evidence integrity |
| Steps | — | B1 `make verify` · B2 `make docs-verify` · B3 `harness.replay --verify-suite` · B4 `freeze_release --verify` |

`docs/DEMO.md` documents both, plus five copy-pasteable manual probes, an evidence→claim table, and an honest "what to say if a step fails" table.

**One documented probe was wrong and was fixed:** probing `score_episode` on the checked-in `episodes/dev/*` fails, because those directories intentionally carry no `sealed/truth.json` (sealed-data git policy `D-01-04`). The corrected probe builds a twin in a temp dir first. This is exactly the class of error the phase is about — a plausible-looking instruction that does not run.

## 5. Verification evidence (commands run in this session)

| Command | Exit | Result |
|---|---:|---|
| `make lint` | 0 | CLEAN (REQ-ARC-001..007) |
| `make verify` (working tree) | 0 | **12/12 PASS**, 61.9 s, 21 artifacts |
| **`make verify` (clean tree, `git ls-files` copy, empty evidence dir)** | **0** | **12/12 PASS**, 61.1 s — docs gate PASS after artifacts exist |
| `make docs-verify` | 0 | **23 measured facts, 11 checks**, PASS |
| `make demo` (`tools/demo_walkthrough.py`) | 0 | 5 segments, seed 2025, `full_os_sandbox=True` |
| `make demo-backup` | 0 | **PASS** — all four probes green |
| `python3 -m unittest tests.judge.test_doc_claims` | 0 | 18 tests OK |
| `python3 -m unittest tests.judge.test_doc_claims tests.judge.test_judge_kit` | 0 | 56 tests OK |
| `python3 tools/freeze_release.py --verify` | 0 | 30 frozen files intact (`0747baf0…`) |
| `make verify` in simulated read-only container layout | 0 | 12/12 PASS — doc-claims report degrades gracefully |
| `make verify` with tmpfs-masked `artifacts/trajectories` | 0 | 12/12 PASS — baselines reported as omitted, no false drift |
| `tools/verify_doc_claims.py` with unwritable output path | 0 | PASS verdict preserved, note printed |
| full suite via RC-001 | 0 | **477 tests**, 1 optional skip (critical_skipped=0) |
| `make verify` ×2 consecutive, then `docs-verify` | 0 | stable — no drift |

### 5.1 Negative tests (the gate must actually fail)

| Injected fault | Observed |
|---|---|
| Corrupt a number inside the generated block (`410` → `317`) | `[DRIFT] G-BLOCK`, exit 1 |
| Reintroduce `317 tests` prose | `[STALE_LITERAL] D-STALE`, exit 1 |
| Break a prose count (`5/5` → `4/5`) | `[STALE] P-REPLAY`, exit 1 |
| Cite `D-99-99` | `[PHANTOM_ID] R-DECISION-ID`, exit 1 |

## 6. Files

**Added:** `docs/API_USAGE.md`, `docs/POLICY_PROTOCOL.md`, `docs/DEMO.md`, `tools/verify_doc_claims.py`, `tests/judge/test_doc_claims.py`, this report.
**Rewritten:** `docs/DESIGN.md` (as-built), `README.md` (measured facts block, protocol note, docs index).
**Corrected:** `docs/LIMITATIONS.md` (canary enumeration), `docs/THREAT_MODEL.md` (fake transform list), `Makefile` (`docs-verify`, `demo`, `demo-backup`).
**Frozen files changed:** none. `contracts/*`, `configs/*`, `judge/rubric_map.json`, Master TZ untouched; freeze verify PASS.

## 7. Deviations & limitations

1. `README.md` is now partly generated. Editing the block by hand is a gate failure by design; use `--write`.
2. `docs/DATA_DICTIONARY.md` was left substantially intact — it was already accurate about the public schema. It is covered by the placeholder/denylist scan but its field list is not individually re-derived from the schemas.
3. The doc-claims gate proves *documentation matches artifacts*. It cannot prove the artifacts themselves measure the right thing — that is the job of RC-001..RC-012.
4. Sampled performance numbers remain available in `performance_report.json` but are deliberately not asserted in docs (see §3.1).
5. `make demo-backup` re-runs the full `make verify` (~63 s), so it is a reviewer tool, not a per-commit gate.
6. **L-H:** the claimed baseline numbers derive from `artifacts/trajectories/trajectories.jsonl`, which `make verify` does not regenerate (it is produced by `make official-eval` and committed). Regenerating it is a manual reviewer step, not part of the gate.

## 8. Next-phase readiness (Phase 16 — release candidate)

- Jury path is now self-verifying: `make verify` → `make docs-verify` → `make demo-backup`.
- Every published claim resolves to an artifact in `artifacts/reports/latest/` or `artifacts/reports/doc_claims/`.
- Phase 16 items still open by design: clean-clone `make verify` on a fresh CI runner, offline Docker re-run, tag + GitHub release.

**Sign-off:** Phase 15 re-audit complete. EXIT GATE 15 PASS with the command output above. Release/tag authority remains outside this phase.
