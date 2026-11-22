# FIX_VERIFICATION_MATRIX

Every accepted defect, the test that proves it, and the measured behaviour on
the old and new code. "Old code" was measured by
`git stash push -- <file>` and re-running the same test, not by assumption.

| Bug | Sev | File | Fix commit | Regression test | Old code | New code | Status |
|---|---|---|---|---|---|---|---|
| BUG-TL-0001 | P0 | scoring/reward.py | ca04f3f | tests/scoring/test_reward_sanity.py (15 vectors) | 8 vectors fail on old formula | PASS | VERIFIED |
| BUG-TL-0001 | P0 | scoring/reward.py | ca04f3f | tests/unit/test_property.py::test_scoring_stays_in_unit_interval | asserted reward >= 0, now fails | PASS | VERIFIED |
| BUG-TL-0001 | P0 | scoring/reward.py | ca04f3f | tests/scoring/test_reward_properties.py::test_p5_step_penalty_bounded_by_official_weight | P5 bound was eta=0.05 | PASS | VERIFIED |
| BUG-TL-0001 | P0 | judge/mutation_suite.py | ca04f3f | make mutation-test | 23/26 (3 disarmed) | 26/26 | VERIFIED |
| BUG-TL-0002 | P0 | env/cursors.py | ca04f3f | tests/env/test_cursor_codec.py::test_every_offset_round_trips | BAD_CURSOR at offsets 1,7,... | PASS (1000/1000) | VERIFIED |
| BUG-TL-0002 | P0 | env/cursors.py | ca04f3f | tests/env/test_cursor_codec.py::test_offsets_that_broke_the_delimiter_layout | FAILED | PASS | VERIFIED |
| BUG-TL-0002 | P0 | env/cursors.py | ca04f3f | official C05 end-to-end (L fixture, 4 tables) | ledger stops at 150/214 | 214/214, 5 pages | VERIFIED |
| BUG-TL-0003 | P1 | env/cursors.py | ca04f3f | tests/env/test_cursor_codec.py::test_trailing_garbage_rejected | token+'x' ACCEPTED | rejected | VERIFIED |
| BUG-TL-0003 | P1 | env/cursors.py | ca04f3f | tests/env/test_cursor_codec.py::test_non_canonical_trailing_bits_rejected | ACCEPTED | rejected | VERIFIED |
| BUG-TL-0003 | P1 | env/cursors.py | ca04f3f | tests/env/test_environment.py::test_pagination_opaque_cursors_and_tamper_rejection | passed by luck | PASS for the right reason | VERIFIED |
| BUG-TL-0004 | P1 | tests/official/test_block1_contracts.py | ca04f3f | tests/official/test_block1_contracts.py::test_C05... | PASSED on buggy code | fails on old code, PASS on new | VERIFIED |

## Gates re-run after all fixes

| Gate | Command | Result |
|---|---|---|
| Full suite | `python3 -m unittest discover -s tests` | 502 tests, 18 skips, OK |
| Official blocks | `python3 -m unittest discover -s tests/official` | 55 tests, OK |
| Judge Kit | `make verify` | PASS 12/12 (72.4 s) |
| Clean-tree Judge Kit | `git archive` + empty artifacts + no git | PASS 12/12 (65.8 s) |
| Lint / import boundary | `make lint` | CLEAN |
| Determinism | `make replay-all` | PASS 80/80, 567 steps |
| Mutation | `make mutation-test` | 26/26 killed |
| Release audit | `make release-audit` | PASS 6/6 |
| Release candidate | `make rc-check` | PASS |
| Doc claims | `make docs-verify` | PASS (22 facts, 11 checks) |
| Freeze | `freeze_release.py --verify` | 30 files, `0747baf0…` |
| Performance | `make verify` → RC-012 | PASS, p99 0.125 ms |
| Docker | `make docker-check` | **UNVERIFIED** (no docker binary) |

## Checks executed with no defect found

C01–C04, C06–C20; Block 2 (20 episodes); Block 3 vectors 1–20; M01–M12;
Block 4 P01–P20; adapter interface (3 exports, `score_episode` invalid-submit
`return=-1` with null metrics); train/closed reward separation; 60 s limit at
59.9/60.0/61.0 s; end-to-end adapters; secrets scan; import boundary scan;
20-fixture truth/provenance containment; dependency surface (109 modules,
0 external).

No defect was found in those. That is not proof they are defect-free — it is
the list of what was actually executed.
