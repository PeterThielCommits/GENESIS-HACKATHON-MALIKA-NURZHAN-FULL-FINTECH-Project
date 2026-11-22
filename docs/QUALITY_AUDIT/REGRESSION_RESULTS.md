# REGRESSION_RESULTS — post-remediation

All numbers produced on branch `arena/45dc3a73-…` at `0afdbd8` (fixes in
`ca04f3f`). Commands are quoted verbatim.

## Suite results

```
$ python3 -m unittest discover -s tests -t . -q
Ran 502 tests in 43.9s
OK (skipped=18)

$ python3 -m unittest discover -s tests/official -t . -q
Ran 55 tests in 5.7s
OK

$ make mutation-test
[PASS] mutation suite: 26/26 killed (100.0%)

$ make replay-all
replay-all: PASS (80/80 runs, 567 steps byte-identical)

$ make lint
import boundary scan: CLEAN (REQ-ARC-001..007)
```

## Judge Kit

```
$ make verify
[PASS] RC-001 (REQ-CONTRACT-001) (47.69s)
[PASS] RC-002 (REQ-ARC-001) (0.31s)
[PASS] RC-003 (REQ-CONTRACT-010) (0.16s)
[PASS] RC-004 (OFFICIAL-2026-11-20) (5.69s)
[PASS] RC-005 (REQ-SEAL-030) (5.42s)
[PASS] RC-006 (REQ-NLP-004) (2.47s)
[PASS] RC-007 (REQ-ARENA-001) (1.70s)
[PASS] RC-008 (REQ-SHORTCUT-001) (4.82s)
[PASS] RC-009 (REQ-LEAK-001) (0.65s)
[PASS] RC-010 (REQ-TEST-002) (0.17s)
[PASS] RC-011 (REQ-TEST-004) (2.84s)
[PASS] RC-012 (REQ-OPS-001) (0.51s)
verify: documentation claims PASS (docs match measured artifacts)
verify: PASS (72.417s)
```

## Release gates

```
$ make release-audit
[PASS] SECRETS / FILELIST / SIZE / DEPS / ENTRYPOINT / SUBMISSION
release-audit: PASS (6/6 checks)
       498 tracked files, 0 forbidden path(s)
       498 files, 5530451 bytes (budget 1000 files, 52428800 bytes)
       109 runtime modules parsed, 0 undeclared external import(s)
       3 exports verified from cwd=/, reset/2-tuple, step/5-tuple, 5/5 tool names accepted

$ make rc-check
rc-check: PASS (release candidate is consistent)

$ python3 tools/freeze_release.py --verify
[PASS] freeze_release --verify: 30 frozen files intact (aggregate_sha256=0747baf087b9509a...)
```

## Clean-extraction reproducibility

```
$ git archive 0afdbd8 | tar -x -C /tmp/repro
$ rm -rf artifacts/reports/latest artifacts/reports/latest/.gitkeep artifacts/trajectories/*
$ PATH=<no git> LC_ALL=C LANG=C PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 make verify
verify: PASS (65.836s)
```

## Regression-specific evidence (old code vs new code)

| Test | Old code | New code |
|---|---|---|
| `test_cursor_codec::test_every_offset_round_trips` | `BAD_CURSOR` at offset 1 | PASS 1000/1000 |
| `test_cursor_codec::test_trailing_garbage_rejected` | ACCEPTED (2 failures) | PASS |
| official C05 (strengthened) | `BAD_CURSOR` at `ledger page 3` | PASS, 214/214 rows |
| `test_reward_sanity` (15 vectors) | 8 failures | PASS |
| `test_p5_step_penalty_bounded_by_official_weight` | fail (0.05 bound) | PASS |
| `test_scoring_stays_in_unit_interval` | fail (asserted ≥ 0) | PASS |
| mutation suite | 23/26 | 26/26 |

## Checks that could not run

| Command | Result |
|---|---|
| `make docker-check` | `make[1]: docker: No such file or directory` → **UNVERIFIED** |
| `make docker-build` | same → **UNVERIFIED** |

These are not reported as PASS anywhere in this audit.
