# Next agent — Phase 9 (Processes + Seal + Receipts)

All upstream Phases 1–8 are now integrated and green on the frozen `v1.0.0`
contract line (`CR-06-01` resolved, 10/10 generated episodes in `episodes/dev`
and `episodes/train` verified with `release_blocked=False`).

Read before starting:
- `docs/CURRENT_STATE.md`
- `docs/STATUS.md`
- `docs/PHASE_REPORTS/PHASE-08.md`
- `contracts/receipt.schema.json`, `contracts/trajectory_event.schema.json`
- `tools/check_import_boundaries.py`

Start command:
```bash
make verify && python3 tools/make_dataset.py --split all
```

Owner: Zone 2 (`seal/`, `harness/`). Implement Phase 9 strictly obeying import
boundaries (`seal/` → `contracts/` + stdlib only; `harness/` ↛ `gen/verifier/scoring/seal`)
and frozen `contracts/{receipt,trajectory_event}.schema.json`.
