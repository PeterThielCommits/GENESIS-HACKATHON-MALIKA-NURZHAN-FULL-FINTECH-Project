# TwinLedger — Rubric Traceability (provisional)

`judge/rubric_map.json` is `provisional: true` (D-01-06). Official
organiser checks are unknown (Q-012). Internal checks below are **not**
official checks.

| Internal check | REQ | Test | Command | Artifact |
|---|---|---|---|---|
| RC-001 contracts validated | REQ-CONTRACT-001 | `tests/contracts/test_contracts.py` | `make test` | `artifacts/reports/latest/verify_summary.json` |
| RC-002 canonical determinism | REQ-CONTRACT-010 | `tests/unit/test_canonical.py` | `make test` | same |
| RC-003 import boundaries | REQ-ARC-001 | `tests/unit/test_import_boundaries.py` | `make lint` | same |

When the official rubric is published: copy to `docs/official/`, add
one mirror test per official check, set `provisional: false` only for
confirmed items, and record the change as a CR.
