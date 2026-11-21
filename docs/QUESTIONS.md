# TwinLedger — Open Questions (Phase 0)

Owner: A0 Orchestrator. Closure: official organiser answer + DECISIONS update.

| ID | Question | Status | Blocks |
|---|---|---|---|
| Q-001 | Exact tools, args, responses, error semantics? | OPEN | Phase 5 adapter |
| Q-002 | Exact reset/step, observation, termination rules? | OPEN | Phase 5 |
| Q-003 | Exact finding schema, ID rules, array limits? | OPEN | Phase 6 |
| Q-004 | Exact anomaly taxonomy + accounting semantics? | OPEN | Phase 4/7 |
| Q-005 | Exact reward formula, match criteria, tolerance, duplicates? | OPEN | Phase 6 |
| Q-006 | Exact affected IDs per type? | OPEN | Phase 4/7 |
| Q-007 | Separate scorer process allowed / harness given? | OPEN | Phase 9 |
| Q-008 | Submission format: repo/archive/Docker/entrypoint? | OPEN | Phase 16 |
| Q-009 | Python version, network, CPU/RAM/disk, allowed deps? | OPEN | Phase 1 (assumed 3.11/offline) |
| Q-010 | Sealed reference allowed; how protected from policy? | OPEN | Phase 9 |
| Q-011 | Optional packages / vendor wheels allowed? | OPEN | Phase 1 (assumed optional) |
| Q-012 | What do official rubric checks actually test? | OPEN | Phase 14 |
| Q-013 | When is reward returned: step/submit/finalize? | OPEN | Phase 5/6 |
| Q-014 | Gymnasium-native API required or compatibility only? | OPEN | Phase 10+ |

Assumptions A-001…A-016 (Master TZ 2.2) remain UNRESOLVED until these
are answered. Provisional values live in `configs/` + `adapter/`.
