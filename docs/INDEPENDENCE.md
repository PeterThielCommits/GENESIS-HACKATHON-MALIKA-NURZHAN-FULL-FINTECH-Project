# TwinLedger — Verifier Independence

## Ownership

- Generator (Zone 1): Owner A.
- Verifier (Zone 3): Owner C (different human owner, REQ-ORG-001).
- Verifier receives `contracts/`, `spec/`, public data only — never
  `gen/`, provenance, mutation params or truth at discovery (REQ-ORG-002).

## Implementation boundaries (Phase 1 status)

- `verifier/` must not import `gen/` (REQ-VER-002); enforced by
  `tools/check_import_boundaries.py` (REQ-ARC-001) and
  `tests/unit/test_import_boundaries.py`.
- Verifier discovery accepts only public data (REQ-ARC-007).
- Truth is compared only *after* discovery via a separate crosscheck
  step (REQ-VER-021).
- Common-mode dependencies (e.g. shared money helper) must be reported
  here when introduced (TZ 12.4). Phase 1: none yet (no money helper).

## Evidence

- `make lint` → `import boundary scan: CLEAN`.
- `tests/unit/test_import_boundaries.py` → 6 tests PASS (incl. negative
  detection tests on temp fixtures).

## Known shared dependencies

None at Phase 1. `contracts/` (schemas + canonical JSON) is the only
shared code, which is allowed (TZ 3: shared schemas/spec, not shared
detection algorithms).
