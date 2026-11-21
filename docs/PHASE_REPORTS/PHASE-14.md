# Phase 14 Report — JUDGE KIT & FULL REPORT (re-audit)

- **Status:** `DONE` — `EXIT GATE 14: PASS` (clean-checkout reproduction, evidence below)
- **Date:** `2026-11-21`
- **Branch:** `arena/102582b5-genesis-hackathon-malika-nurzh`, base `e9a4239` (`Merge PR #17`, `main`)
- **Phase tasks:** 14.1 rubric_map · 14.2 `make verify` + exit codes · 14.3 artifact report schemas · 14.4 CSV/JSON summary · 14.5 optional offline HTML · 14.6 phase report template + automatic artifact index
- **Requirements:** `REQ-JUDGE-001`, `REQ-JUDGE-002`, `REQ-JUDGE-003`, `REQ-JUDGE-004`, `REQ-JUDGE-005`, `REQ-OPS-001`, `REQ-OPS-002`, `REQ-OPS-003`
- **Decisions:** `D-14-01` (prior), **`D-14-02` (new)**, **`D-14-03` (new)**
- **Supersedes:** the earlier Phase 14 report on branch `arena/3a99279e…`, whose EXIT GATE claim was measured only in a **dirty** working tree (pre-existing `artifacts/reports/latest/`), so it did not actually demonstrate TZ §24 EXIT GATE 14 ("чистая checkout + documented command").

## 1. Scope of this re-audit

Phase 14's own exit gate is *not* "the 12 gates pass" — that is Phase 13's boundary. It is:

> **EXIT GATE 14: clean checkout + documented command → complete verification outputs.**

The earlier report claimed PASS from a tree that already contained 21 artifacts. Re-running the gate the way the TZ defines it exposed **three real defects** (all in non-frozen files) plus **four contract gaps**. All are fixed below; frozen files were not touched (`python3 tools/freeze_release.py --verify` → PASS, 30 files, `0747baf0…`).

## 2. Defects found and fixed

### 2.1 Clean checkout crashed `make verify` (release-gate defect)

`judge/report.py::_build_html_report` used `x or {{}}` **inside f-string replacement fields**. The `{{`/`}}` escape applies only to literal text; inside an expression it parses as the set literal `{ {} }`, so `.get(...)` raised `TypeError: unhashable type: 'dict'` **only when the left operand was falsy** — i.e. exactly when no prior artifact existed. A dirty tree always had `robustness_report.json` / `reward_strategy_report.json`, so this never fired in earlier runs. Fixed by binding defaults to real dicts before the f-string (`req_checks`, `rob_sum`, `attacks`) with a warning comment. Locked by `tests/judge/test_judge_kit.py::TestOfflineHtmlGuarantee::test_build_report_survives_empty_artifact_dir`.

### 2.2 Report synthesis ran before its own input existed (ordering defect)

`judge/verify.py` called `judge/report.py` **before** writing `verify_summary.json`, so on a clean checkout `report.py` exited 5 ("no verify_summary.json found"), which poisoned the whole run to exit 5 even with 12/12 PASS. Fixed by splitting summary emission into `_write_summary()` and running it in two phases: **phase A** before the report step (so the report has its input), **phase B** after `report.html`/`report_index.json` exist (final status, artifact list, contract errors).

### 2.3 Pre-report completeness check permanently marked the run incomplete (logic defect)

The advisory pre-report `check_artifact_completeness()` (which must report `report.html`/`report_index.json` as missing at that moment) set `incomplete = True` unconditionally, forcing exit 5. It is now advisory-only (prints which artifacts are still pending); only the **final** completeness pass after `report.py` may set exit 5.

### 2.4 `Replay Suite: 0/0` in the HTML report (silent metrics bug)

`judge/report.py` read `replay.get('episodes_matched')` / `episodes_tested`, which `harness/replay.py` never wrote, so the auditor-facing report silently showed **0/0** while 5/5 replays actually matched. `harness/replay.py` now emits `episodes_tested` / `episodes_matched`; the rendered report shows `5/5`.

### 2.5 TZ §23.5 metadata envelope missing on 2 reports (contract gap)

TZ §23.5 requires **every** report to carry code version, config hash, run timestamp, target platform, Python version and launch command. `replay_report.json` was missing 4 of 6 fields, `reward_property_matrix.json` all 6. Both now emit the full envelope. A new stdlib validator (`judge/schemas.py::validate_report_envelope` / `validate_report_dir_envelopes`) audits **every** `*.json` in `artifacts/reports/latest/` at the end of `make verify`; violations are a contract error (**exit 2**).

### 2.6 Exit-code and skip-accounting hardening (Phase 14.2)

- `parse_skipped_counts()` separates **optional** (`hypothesis`/extra-not-installed) from **critical** skips; unattributed `skipped=N` is treated as critical (fail-conservative).
- `classify_check()` is a pure function mapping subprocess exit → `PASS/FAIL/SKIPPED/BLOCKED` + `release_blocked` / `resource_err` / `incomplete` flags.
- Precedence is deterministic: **4 > 3 > 2 > 1 > 5 > 0**.
- `report.py` no longer dies with an uncaught `RuntimeError` on an offline-HTML violation: it exits **4** (release blocker). A malformed `verify_summary.json` exits **2**.

### 2.7 Rubric map / schemas (Phase 14.1, 14.3)

- `judge/rubric_map.json` is **frozen**; the validator (`judge/schemas.py`) requires the 7 contract fields and checks `schema_version` only when present — the frozen map carries the version once at top level (`rubric_version`), matching `contracts/rubric_check.schema.json` intent (**D-14-02**).
- `rubric_matrix.csv` now carries `rubric_item` + `provisional` columns, so each gate is traceable to a rubric item and its provisional status.
- `judge/performance_and_deps.py` reports **INV-01..INV-17** (was hardcoded 15) and no longer raises `IndexError`/`KeyError` when `episodes/dev/` or metrics are absent (guarded, error-report path).

### 2.8 Phase report template (Phase 14.6)

`docs/PHASE_REPORTS/TEMPLATE.md` did not exist; added per TZ §23.7 (scope, REQ IDs, commits, changed files, commands, results, failed tests, deviations, limitations, next phase, sign-off).

## 3. Verification evidence (commands run in this session)

All commands were run from the repository root, Python 3.11.2, Linux 6.1.

| Command | Exit code | Result |
|---|---:|---|
| `python3 -m unittest tests.judge.test_judge_kit -v` | 0 | **38 tests OK** (new Judge Kit suite) |
| `make lint` | 0 | compile + `CLEAN (REQ-ARC-001..007)` import-boundary scan |
| `python3 -m unittest discover -s tests -t .` | 0 | **410 tests, OK** (skipped=1, optional Hypothesis extra) |
| `make verify` | 0 | **12/12 PASS** in 63.3 s, 21 artifacts |
| `make verify-core` | 0 | **6/6 PASS** in 48.0 s |
| `make report` | 0 | `report.html` + `report_index.json` (21 artifacts) |
| `make test-property` | 0 | 17 tests OK (1 optional skip) |
| `python3 tools/freeze_release.py --verify` | 0 | **30 frozen files intact**, aggregate `0747baf0…` |
| **`make verify` in a clean copy** (git-tracked files only, `artifacts/reports/latest/` containing only `.gitkeep`) | **0** | **12/12 PASS**, 62.1 s — *this is the phase exit gate* |

### 3.1 Clean-checkout gate evidence

Fresh tree built from `git ls-files` (no `__pycache__`, empty evidence directory):

```
verify: artifacts pending synthesis before report step: verify_summary.json, verify_summary.txt
report: synthesized report.html + report_index.json (21 artifacts)
verify: PASS (62.055s) — artifacts/reports/latest/verify_summary.json
```

Post-run audit of that clean output:

```
files: 20            (19 JSON/CSV/MD + report.html; verify_summary.txt += 21 artifacts)
envelope errors: []
status PASS | checks {'total': 12, 'passed': 12, 'failed': 0, 'blocked': 0, 'skipped': 0}
optional {'passed': 2, 'skipped': 2, 'critical_skipped': 0}
missing []           | schema_err []
official_score_claimed False | pass_rate 100.0
replay: 5 / 5 PASS (config_hash 7db96eb029fdb566…)
html http count: 0   | report renders 'Replay Suite: 5/5'
index artifacts 21, missing [], offline_self_contained_html True
```

### 3.2 Exit-code contract (negative tests, exercised manually)

| Scenario | Observed | TZ §23.3 target |
|---|---:|---|
| `judge/verify.py --full` with malformed `judge/rubric_map.json` | **2** | 2 = configuration/contract error |
| `judge/report.py` with no `verify_summary.json` | **5** | 5 = suite not complete |
| `judge/report.py` with malformed `verify_summary.json` | **2** | 2 |
| Offline-HTML violation (unit-tested path) | **4** | 4 = release blocker |
| `--full` clean checkout, all green | **0** | 0 |

Frozen file was restored byte-identically after the malformed-map test (`sha256 …e1674f18`, `freeze --verify` PASS).

## 4. Performance & dependency budgets (RC-012, refreshed)

- env step p99 **0.17 ms** (budget < 5.0 ms) over 180 samples
- peak RSS **22.41 MB** (budget < 300 MB)
- max episode disk **0.081 MB** (budget < 50 MB)
- core stdlib-only audit: no third-party import in core packages; Docker base pinned to `python:3.11`, `USER 10001`, `@sha256:` digest

## 5. Files changed (non-frozen only)

| File | Change |
|---|---|
| `judge/verify.py` | two-phase summary emission, advisory pre-report completeness, envelope+index schema gate (exit 2), `artifact_schema_errors` field |
| `judge/report.py` | f-string set-literal crash fixed; required dicts bound before rendering |
| `judge/schemas.py` | **new** stdlib validators: rubric_map, verify_summary, report_index, TZ §23.5 report envelope |
| `judge/performance_and_deps.py` | INV-01..INV-17, missing-`episodes/dev` and empty-record guards, metrics-safe `main()` |
| `harness/replay.py` | TZ §23.5 envelope + `episodes_tested` / `episodes_matched` |
| `tests/scoring/test_reward_properties.py` | TZ §23.5 envelope on `reward_property_matrix.json` |
| `tests/judge/__init__.py`, `tests/judge/test_judge_kit.py` | **new** 38-test Judge Kit suite |
| `docs/PHASE_REPORTS/TEMPLATE.md` | **new** TZ §23.7 phase report template |
| `docs/PHASE_REPORTS/PHASE-14.md` / `.json` | this report |
| `docs/CURRENT_STATE.md`, `docs/STATUS.md`, `docs/DECISIONS.md` | phase closure, D-14-02 / D-14-03 |

No `contracts/*`, no `configs/*`, no `judge/rubric_map.json`, no Master TZ change. Freeze manifest unchanged.

## 6. Failed / skipped checks

- **Skipped (optional, expected):** 1-2 tests requiring the optional `hypothesis` extra (TZ §20.2 optional dependencies). Recorded explicitly in `verify_summary.json → optional_checks` (`skipped: 2`, `critical_skipped: 0`) and printed in `verify_summary.txt` — never silently omitted (`REQ-JUDGE-003`).
- **Failed:** none.

## 7. Deviations & limitations

1. `make verify` is not bit-identical across runs by design: timestamps and durations are excluded from deterministic hashes (TZ §23.5).
2. The rubric weights (25/25/25/15/10) and the 12 RC gates are **provisional** and are never presented as the organiser's score (`official_score_claimed: false`, `REQ-JUDGE-005`, TZ §23.6).
3. `harness/replay.py` and `tests/scoring/test_reward_properties.py` were touched although they are Zone-2/Zone-1 test-adjacent files: the change is additive metadata only (no behaviour, reward or replay semantics), required by TZ §23.5, and verified by the full suite.
4. Offline guarantee is enforced by static audit of generated HTML (no `http(s)://`, no external `src`/`href`/`url()`), not by an OS-level network namespace in this phase.

## 8. Next-phase readiness (Phase 15 — documentation & demo)

- Evidence directory now *self-describing*: every JSON report carries the §23.5 envelope, `report_index.json` lists all 21 artifacts with no missing entries.
- `report.html` renders real replay counts and all 12 gates — usable as a jury artifact.
- README's stale "317 tests / 21 artifacts" claim should be corrected in Phase 15 against measured 410 tests.

## 9. Merge record

| Item | Value |
|---|---|
| Pull request | **#18** — *Phase 14 re-audit: Judge Kit & full report — EXIT GATE 14 verified on clean checkout* |
| Branch | `arena/102582b5-genesis-hackathon-malika-nurzh` → `main` |
| Head commit | `baa5b67` |
| Merge commit | `99df116` (merged 2026-11-21T23:43:03Z) |
| Merge strategy | merge commit (history preserved) |
| CI | `core` PASS (1m33s), `docker-offline` PASS (1m56s) |
| Tree equality | merged `main` tree `1a451cb8…` == verified branch tree `1a451cb8…` (byte-identical) |
| Post-merge `make verify` on `main` | **PASS**, 12/12, 50.1 s, 21 artifacts |
| Post-merge `freeze_release --verify` | 30 frozen files intact (`0747baf0…`) |

The merged tree is byte-identical to the verified head commit, so the clean-checkout EXIT GATE 14 evidence above applies unchanged to `main` at `99df116`.

**Sign-off:** Phase 14 re-audit complete and merged. EXIT GATE 14 PASS on clean checkout with recorded command output above. Release/tag authority remains outside this phase.
