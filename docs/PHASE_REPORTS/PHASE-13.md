# Phase 13 — Metamorphic, property and mutation tests

**Status: DONE; EXIT GATE 13: PASS.** Re-audit 2026-11-21; branch `arena/9d42d276-genesis-hackathon-malika-nurzh`, base `fa3b2919fe375bce849e7bcdf16e38365be04c32`. [Tracking issue #16](https://github.com/PeterThielCommits/GENESIS-HACKATHON-MALIKA-NURZHAN-FULL-FINTECH-Project/issues/16). Requirements: REQ-TEST-001–005, REQ-CONTRACT-010.

| Task | Evidence |
|---|---|
| 13.1 Metamorphic | `metamorphic/suite.py`: M-01–M-07, verifier equivariance and budget-aware policy reward equality, four scenarios including compound; 28 pairs. Public bytes differ for each pair. |
| 13.2 RNG isolation | `tests/generator/test_rng_isolation.py`: captures actual pipeline clean twins for four operator plans, tests scoped RNG streams and representative text/injection variations. |
| 13.3 Evidence ablation | `tests/verifier/test_evidence_ablation.py`: four anomaly types, sufficiency, single-element deletion, reachability and minimality. |
| 13.4 Mutation | `judge/mutation_suite.py`: 26 instrumented mutant classes, 26 killed; deterministic tie-break repeat fault and explanatory assertion messages. `tests/scoring/test_differential.py` compares matcher against brute force. |
| 13.5 Property | `tests/unit/test_property.py`, `tests/unit/test_phase02.py`, `tests/scoring/test_reward_properties.py` and metamorphic/isolation suites: stdlib loops plus optional Hypothesis checks. |
| 13.6 Interleaving | `tests/env/test_interleaved_isolation.py`: three environments versus isolated runs. |

## Verification (2026-11-21)

- `make verify` — exit 0, all 12 gates PASS, including RC-003/010/011.
- `python3 -m unittest discover -s tests -t .` — exit 0, 372 tests, one skipped (Hypothesis absent from core environment).
- `make test-property` — exit 0, 17 tests, one skipped (same optional dependency).
- `python3 -m pip install --quiet --target /tmp/tl-phase13-hypothesis 'hypothesis>=6' && PYTHONPATH=/tmp/tl-phase13-hypothesis python3 -m unittest tests.unit.test_property -q` — exit 0, 18 tests, no skips. Installation was isolated from the project.
- `python3 judge/mutation_suite.py` — exit 0, 26/26 killed. `python3 metamorphic/suite.py` — exit 0, 7/7, 28 pairs. Latest machine-readable reports: `artifacts/reports/latest/mutation_test_report.json` and `metamorphic_report.json`.
- `make replay` — exit 0, 5/5 byte-identical. `make audit-shortcuts` — exit 0. `make lint` — exit 0. `python3 tools/freeze_release.py --verify` — exit 0, 30 frozen files intact.

These are finite test cases, not proofs of universal invariance. The byte-difference guard detects a no-op transformation, not a guarantee that every intended field was transformed. RNG-order serialized truth differences may include ordering/IDs and do not by themselves establish a semantic causal change. Hypothesis is optional and its two tests cover only canonical ordering and F1 range; the remaining properties use existing deterministic suites. Mutation results apply to these instrumented fault implementations, not arbitrary faults. No frozen production files were modified. See `docs/DECISIONS.md` D-13-01.
