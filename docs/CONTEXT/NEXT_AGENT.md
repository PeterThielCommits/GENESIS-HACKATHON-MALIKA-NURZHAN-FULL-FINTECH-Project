# Next agent — Phase 12 release handoff
Read AGENTS.md, CURRENT_STATE, PHASE_REPORTS/PHASE-12.md, D-12-01/D-12-02 and
HANDOFF/phase-12-audit.md. Work only on the Arena-assigned active branch.
State: `make verify` 12/12 PASS, `make lint` CLEAN, `freeze --verify` PASS (0747baf0…), PR #15 OPEN.
First action: `python3 tools/freeze_release.py --verify` (expect PASS) and `python3 -m unittest tests.arena.test_arena_and_audits -v` (4/4) + `tests.env.test_loader_order_and_bounds` (11/11).
Do not re-freeze without new code change; D-12-02 documents the authorized re-sync. Docker runtime pending CI `docker-offline`.
Human owner: QA/release maintainer, not yet assigned.
