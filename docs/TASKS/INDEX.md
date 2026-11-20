# Task index

One row per task card. Status vocabulary is the same as `docs/STATUS.md`; "DONE" always means a
report or a command exists, not that someone remembered doing it.

| Task | Phase | Status | Report / evidence |
|------|-------|--------|-------------------|
| `T-0-01` official source discovery | 0 | DONE | `docs/official/SOURCE_SEARCH_LOG.md`, `docs/PHASE_REPORTS/PHASE-00.md` |
| `T-0-02` contract extraction | 0 | DONE | `docs/REQUIREMENTS.json`, `docs/ASSUMPTIONS.json` |
| `T-0-03` decisions and questions | 0 | DONE | `docs/DECISIONS.md`, `docs/QUESTIONS.md` |
| `T-0-04` contracts v0.1 | 0 | DONE | `contracts/`, `CT-CONTRACTS-01/02` |
| `T-0-05` isolation of unknowns | 0 | DONE | `adapter/`, `configs/`, `CT-ADAPTER-01` |
| `T-0-06` risk register | 0 | DONE | `docs/RISK_REGISTER.md`, `docs/THREAT_MODEL.md` |
| `T-0-07` verification harness | 0 | DONE | `tools/verify.py`, `artifacts/reports/latest/` |
| `T-0-08` phase report and handoff | 0 | DONE | `docs/PHASE_REPORTS/PHASE-00.md`, `docs/HANDOFF/` |
| `T-1-01` contracts hardening (CI, models, freeze) | 1 | DONE | `docs/PHASE_REPORTS/PHASE-01.md` |
| `T-2-01` money primitives | 2 | NOT STARTED | `docs/TASKS/T-2-01-money-primitives.md` |
| `T-3-01` deterministic generator | 3 | NOT STARTED | `docs/TASKS/T-3-01-deterministic-generator.md` |
| `T-4-01` anomalies and truth | 4 | NOT STARTED | `docs/TASKS/T-4-01-anomaly-and-truth.md` |
| `T-5-01` environment contract | 5 | NOT STARTED | `docs/TASKS/T-5-01-environment-contract.md` |

Open human actions live in `docs/STATUS.md` §"Human actions required"; they are deliberately not
task cards, because an agent cannot close them and a card would imply otherwise.
