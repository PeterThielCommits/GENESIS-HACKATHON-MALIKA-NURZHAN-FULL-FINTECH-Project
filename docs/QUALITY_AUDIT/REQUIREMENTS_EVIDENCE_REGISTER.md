# REQUIREMENTS_EVIDENCE_REGISTER

Requirement → implementation → evidence → measured result. Only `VERIFIED`
entries have a command output behind them. `UNVERIFIED` is used where the
capability could not be executed in this environment.

| REQ id | Source | Requirement | Implementation | Evidence | Result | Status |
|---|---|---|---|---|---|---|
| REQ-OFF-B1-C05 | spec::Block1::C05 | pagination: all rows reachable | adapter/official_env.py, env/cursors.py | tests/official/test_block1_contracts.py | was FAILED (BUG-TL-0002) | VERIFIED |
| REQ-OFF-B3-FORMULA | spec::Block3::tests1-20 | return = clip([-1,1], 2*F1-1-0.2*steps/100) | scoring/official_scorer.py | tests/official/test_block3_scorer.py | was split across 2 impls (BUG-TL-0001) | VERIFIED |
| REQ-OFF-B3-CLEAN | spec::Block3::test3 | clean book + empty findings -> P=0,R=0,F1=1 | scoring/official_scorer.py | tests/official/test_block3_scorer.py::test_03 | verified | VERIFIED |
| REQ-OFF-B3-LIMITS | spec::Block3::18-20 | 30 findings / 10 evidence / 1000 codepoints -> return -1 | scoring/official_scorer.py | tests/official/test_block3_scorer.py::test_18..20 | verified | VERIFIED |
| REQ-OFF-B3-MATCH | spec::matcher-normalisation | max-cardinality matching, lexicographic tie-break, exact ID/currency/tau | scoring/official_scorer.py | tests/official/test_block3_scorer.py::test_M01..M12 | verified manually + by test | VERIFIED |
| REQ-OFF-B1-C16 | spec::Block1::C16 | submit counts toward 100-action budget but not inspection_steps | adapter/official_env.py | tests/official/test_block1_contracts.py::test_C16 | verified | VERIFIED |
| REQ-OFF-B1-C18 | spec::Block1::C18 | reproducible 60s limit -> truncated, empty findings | adapter/official_env.py | tests/official/test_block1_contracts.py::test_C18 | fake clock; 59.9 accepted / 60.0 truncated | VERIFIED |
| REQ-OFF-B1-C20 | spec::Block1::C20 | no truth/provenance/seed leakage; no shell/SQL/FS/network | adapter/, env/, harness/ | tests/official/test_block1_contracts.py::test_C20 | 7 attack vectors bounded | VERIFIED |
| REQ-OFF-B2 | spec::Block2 | 20 closed episodes verifiable independently | gen/pipeline.py, verifier/ | tests/official/test_block2_episodes.py | 20/20 F1=1 via independent crosscheck | VERIFIED |
| REQ-OFF-B4 | spec::Block4 | 20 paired invariance checks | metamorphic/paired_transform.py | tests/official/test_block4_paired.py | 25 assertions | VERIFIED |
| REQ-OFF-ADAPTER | spec::adapter-interface | generate_episode/make_env/score_episode; invalid submit -> return -1, others null | judge_adapter.py | tests/official/test_block1_contracts.py, tests/judge/ | verified by direct call | VERIFIED |
| REQ-CONTRACT-001 | TZ | frozen contracts intact | contracts/ | tools/freeze_release.py --verify | 30 files 0747baf0... | VERIFIED |
| REQ-SEAL-030 | TZ | replay determinism | harness/replay.py | make replay-all | 80/80 567 steps | VERIFIED |
| REQ-LEAK-001 | TZ | no hidden-truth leakage | judge/, contracts/ | RC-009 canary_fuzz | 0 hits | VERIFIED |
| REQ-TEST-002 | TZ | mutation kill rate | judge/mutation_suite.py | RC-010 | 26/26 | VERIFIED |
| REQ-TEST-004 | TZ | metamorphic equivariance | metamorphic/ | RC-011 | 7/7 transforms, 28 pairs | VERIFIED |
| REQ-OPS-001 | TZ | performance within targets | judge/performance_and_deps.py | RC-012 | p99 0.125ms, RSS 22.4MB | VERIFIED |
| REQ-ARC-001..007 | TZ | import boundaries | all runtime | make lint | CLEAN | VERIFIED |
| REQ-DOCKER | TZ | offline hardened image runs the gate set | Dockerfile, Makefile | make docker-check | not executed | UNVERIFIED |

## Conflicts and provisional items

| ID | Nature | Status |
|---|---|---|
| D-15-02 (`calc` vs `calculator`) | Documented naming asymmetry between the JSONL protocol and the official adapter tool name | Accepted, documented in README + POLICY_PROTOCOL |
| D-18-01 (`eta: 0.05` in frozen config) | Frozen contract value no longer drives the reward | Accepted, documented; frozen file not edited |
| A-002 (anomaly taxonomy) | Team-defined; official text requires two documented interaction scenarios, which we ship | Accepted |
| A-006 (step accounting) | Was provisional; the official border decision confirms it | CONFIRMED by official text |
| Q-005 (reward formula) | Was OPEN; official text fixes it | RESOLVED |
