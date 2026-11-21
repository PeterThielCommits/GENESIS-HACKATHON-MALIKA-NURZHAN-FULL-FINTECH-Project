# Next agent — Phase 12 re-audit handoff
Read AGENTS.md, CURRENT_STATE, PHASE_REPORTS/PHASE-12.md, D-12-01 and
HANDOFF/phase-11-audit.md. Work only on the Arena-assigned active branch.
First action: `python3 tools/freeze_release.py --verify`; investigate stale
contracts/loader.py digest from D-10-03 (env/loader.py restoration already applied in this branch) before proposing an authorized re-freeze.
Do not weaken checks or silently rewrite frozen configs. Phase 12 Arena/shortcut/canary gates are engineering-only; official scorer untouched.
Reproduce `python3 -m unittest tests.arena.test_arena_and_audits -v` and `make verify` (expect 12/12 PASS, 360 tests).
Human owner: QA/release maintainer, not yet assigned.
