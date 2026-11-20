# T-0-06 — Risk register and threat model

| Field | Value |
|-------|-------|
| Phase | 0 (phase title: "реестр рисков") |
| Human owner | A0 orchestrator |
| Status | DONE |
| Requirement ids | §0.3 P0 list, §27 R-01..R-24, REQ-SEAL-001..005 |

## Goal
Record every known risk with an owner, a mitigation and a control that can be pointed at.

## What was done
* `docs/RISK_REGISTER.md`: 5 P0 items + R-01…R-24 + one Phase 0-specific risk, each with
  impact, mitigation, control/evidence, owner and status (`OPEN`/`MITIGATED`/`ACCEPTED`/`WATCH`).
* `docs/THREAT_MODEL.md`: assets, adversaries, 12 boundaries with real status (including three
  "NOT ENABLED" rows), attack surfaces mapped to phases, residual risks.

## Acceptance evidence
| Check | Command | Result |
|-------|---------|--------|
| files exist and are current | `python -m tools.check_governance` (`GOV-DOCS-01`) | PASS |
| no false isolation claim | manual review + `GOV-CLAIMS-01` scan | PASS |

## Honest limitation
Risk statuses are opinions until a control exists; `MITIGATED` is only used where a test or a
governance check enforces the mitigation today.
