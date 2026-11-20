# Phase 2 — local gate PASS (2026-11-20)

| Area | Implementation | Independent evidence |
|---|---|---|
| REQ-MONEY-001…006 | `core/money.py`, frozen `contracts/currency.json` | `tests/fixtures/manual/fx.json`, invalid and ambient precision cases |
| REQ-TIME-001…005 | `core/time_rules.py` | gap, both folds, Almaty control, local month and fiscal quarter boundaries |
| REQ-DATA-001…004 | `core/ids.py`, group checks | order independence, four styles, namespaces, duplicates and references |
| REQ-INV-004…005 | `invariants/checks.py`, `spec/invariants.yaml` | `groups.json` and `edges.json`: five manual cases per invariant |

Python 3.11.2: `make setup lint test verify-core verify` succeeded. Import scan CLEAN;
40 unittest methods passed; three property tests rerun successfully. Both verify
modes passed RC-001…003. Reproduce from repository root; no external service needed.

Group inputs are normalized, not raw episode tables. A producer must partition
by catalog key and currency and supply independently derived policy facts; e.g.
INV-07 checks quote membership, not the market calendar algorithm. The primitive
never chooses or inverts a market quote. Episode-wide clean/mutation checks
(REQ-INV-001…003) require later generator/verifier phases. This gate is not a
claim about those phases or official organizer compatibility. Human sign-off pending.
