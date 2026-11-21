# Next agent — Phase 11 re-audit handoff
Read AGENTS.md, CURRENT_STATE, PHASE_REPORTS/PHASE-11.md, D-11-01 and
HANDOFF/phase-11-audit.md. Work only on the Arena-assigned active branch.
First action: `python3 tools/freeze_release.py --verify`; investigate stale
contracts/loader.py digest from D-10-03 before proposing an authorized re-freeze.
Do not weaken checks or silently rewrite frozen configs. Phase 11 scoring is
internal/provisional and report-only; do not replace the official scorer.
Reproduce `python3 -m unittest tests.nlp.test_phase11_audit -v` and `make verify`.
Human owner: QA/release maintainer, not yet assigned.
