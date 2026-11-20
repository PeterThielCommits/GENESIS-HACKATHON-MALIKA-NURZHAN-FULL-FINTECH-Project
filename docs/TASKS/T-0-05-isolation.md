# T-0-05 — Isolation of unknowns in adapter/ and configs/

| Field | Value |
|-------|-------|
| Phase | 0 (exit-gate criterion) |
| Human owner | A0 orchestrator |
| Status | DONE |
| Requirement ids | REQ-ADAPTER-002, REQ-ADAPTER-003, REQ-CONTRACT-022, REQ-ARC-001..003 |

## Goal
Make it structurally impossible for an unknown external detail to be hardcoded in core logic.

## What was done
* `adapter/compatibility.py` + `configs/adapter/compatibility.json`: a profile with status
  `UNBOUND`; every translation entry point raises `ADAPTER_NOT_BOUND`; an unsupported profile
  version raises `ADAPTER_VERSION_UNSUPPORTED` (no approximation).
* `adapter/organizer.py`: the four required crossing points, implemented as fail-closed stubs
  with a bound-path that only activates for a real profile.
* `configs/`: 9 versioned files holding every provisional number/formula (limits, mode, cursor,
  resources, reward, match, tolerance, generator, rubric, arena).
* `tools/check_import_boundaries.py`: zone table covering directories that do not exist yet.

## Acceptance evidence
| Check | Command | Result |
|-------|---------|--------|
| fail-closed behaviour | `python -m unittest tests.unit.test_adapter_compatibility` | PASS |
| boundaries | `python -m tools.check_import_boundaries` | PASS |
| isolation points exist | `python -m unittest tests.phase0.test_assumption_registry` | PASS |

## Residual risk
The adapter cannot be exercised against the real protocol until Q-001…Q-014 are answered; that
is stated in `docs/LIMITATIONS.md` §1 rather than hidden.
