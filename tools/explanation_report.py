#!/usr/bin/env python3
"""Explanation consistency report generator (Phase 10, Task 10.6 — Master TZ §17.6).

Produces the Phase-10 deliverable artifact ``explanation consistency report``:

  python3 tools/explanation_report.py --demo \\
      --output artifacts/reports/latest/explanation_consistency_report.json

  python3 tools/explanation_report.py --submission submission.json \\
      --episode-dir episodes/EP-001 --output report.json

The report is purely diagnostic (TZ §15.9 / §17.6): it NEVER alters matching,
F1, or official reward. Rules checked per finding (§17.6):
  1. typed IDs in the explanation belong to affected_ids/evidence_ids;
  2. stated amounts agree with claimed_amount (when recognised);
  3. cited currency codes agree with finding.currency;
  4. no asserted fact whose ID is absent from declared evidence;
  5. free-text explanation never influences official reward (invariance is
     property-tested in ``tests/unit/test_property.py``).

Stdlib + in-repo imports only; deterministic output (no wall-clock fields).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.models import Finding  # noqa: E402
from scoring.explanation_linter import lint_findings_explanations  # noqa: E402

REPORT_TYPE = "explanation_consistency"
REPORT_SCHEMA_VERSION = "1.0.0"

#: TZ §17.6 rule catalogue (documentation field of the report).
RULES: tuple[dict[str, str], ...] = (
    {
        "rule_id": "EC-01",
        "check": "typed IDs mentioned in explanation must belong to affected_ids or evidence_ids",
        "tz_ref": "§17.6",
    },
    {
        "rule_id": "EC-02",
        "check": "recognised amounts in explanation must be consistent with claimed_amount",
        "tz_ref": "§17.6",
    },
    {
        "rule_id": "EC-03",
        "check": "cited currency codes must match finding.currency (FX pairs allowed)",
        "tz_ref": "§17.6",
    },
    {
        "rule_id": "EC-04",
        "check": "no asserted fact whose typed ID is unreachable in public records",
        "tz_ref": "§17.6",
    },
    {
        "rule_id": "EC-05",
        "check": "free-text explanation never influences official reward",
        "tz_ref": "§17.6",
    },
)

#: Deterministic demo corpus exercising every linter rule path.
DEMO_FINDINGS: tuple[dict[str, Any], ...] = (
    {
        # EC-01..EC-04 all green: declared IDs, matching amount & currency.
        "type": "DUPLICATE_PAYMENT",
        "affected_ids": ["INV:1001", "PAY:2001"],
        "claimed_amount": 125000,
        "currency": "KZT",
        "evidence_ids": ["INV:1001", "PAY:2001"],
        "explanation": "Duplicate posting on INV:1001 and PAY:2001 for amount 125000 KZT.",
    },
    {
        # EC-01 violation: PAY:9999 not declared.
        "type": "DUPLICATE_PAYMENT",
        "affected_ids": ["INV:1002", "PAY:2002"],
        "claimed_amount": 90000,
        "currency": "KZT",
        "evidence_ids": ["INV:1002", "PAY:2002"],
        "explanation": "See also PAY:9999 for the same settlement.",
    },
    {
        # EC-03 violation: cites USD against a KZT finding.
        "type": "PARTIAL_PAYMENT_ALLOCATION",
        "affected_ids": ["INV:1003", "PAY:2003"],
        "claimed_amount": 45000,
        "currency": "KZT",
        "evidence_ids": ["INV:1003", "PAY:2003"],
        "explanation": "Shortfall of 45000 USD on the allocation.",
    },
    {
        # EC-02 violation: asserts contradictory amount 777700.
        "type": "PERIOD_CUTOFF",
        "affected_ids": ["JE:3001"],
        "claimed_amount": 31000,
        "currency": "KZT",
        "evidence_ids": ["JE:3001"],
        "explanation": "Cutoff entry JE:3001 differs by 777700 from the period boundary.",
    },
    {
        # Empty explanation: deterministic, non-contradictory.
        "type": "FX_RATE_MISMATCH",
        "affected_ids": ["JE:3002"],
        "claimed_amount": 1200,
        "currency": "KZT",
        "evidence_ids": ["JE:3002", "FX:USD-KZT-2025-03-01"],
    },
)


def _coerce_findings(raw: Any, source: str) -> list[Finding]:
    if isinstance(raw, dict):
        raw = raw.get("findings")
    if not isinstance(raw, list):
        raise ValueError(f"{source}: expected a findings list or {{'findings': [...]}} object")
    out: list[Finding] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{source}: findings[{idx}] must be an object")
        payload = {"schema_version": "1.0.0", **item}
        try:
            out.append(Finding.from_dict(payload))
        except ValueError as exc:
            raise ValueError(f"{source}: findings[{idx}]: {exc}") from exc
    return out


def build_explanation_consistency_report(
    findings: list[Finding],
    *,
    source: str,
    accessible_public_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Assemble the deterministic explanation consistency report (diagnostic only)."""
    lint = lint_findings_explanations(findings, accessible_public_ids=accessible_public_ids)
    return {
        "report_type": REPORT_TYPE,
        "schema_version": REPORT_SCHEMA_VERSION,
        "source": source,
        "diagnostic_only": True,
        "affects_official_reward": False,
        "rules": [dict(r) for r in RULES],
        **lint,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Phase 10 explanation consistency report (diagnostic only).")
    parser.add_argument("--demo", action="store_true", help="run the built-in deterministic rule-coverage corpus")
    parser.add_argument("--submission", type=Path, default=None, help="submission JSON with a 'findings' list")
    parser.add_argument(
        "--episode-dir",
        type=Path,
        default=None,
        help="episode dir used only to resolve publicly accessible IDs for the reachability check",
    )
    parser.add_argument("--output", type=Path, required=True, help="output JSON path for the report")
    args = parser.parse_args(argv)

    accessible: set[str] | None = None
    if args.episode_dir is not None:
        from scoring.official_scorer import collect_accessible_ids_from_episode_dir

        accessible = collect_accessible_ids_from_episode_dir(args.episode_dir)

    if args.submission is not None:
        raw = json.loads(args.submission.read_text(encoding="utf-8"))
        findings = _coerce_findings(raw, str(args.submission))
        source = f"submission:{args.submission.as_posix()}"
    elif args.demo or args.submission is None:
        findings = _coerce_findings(list(DEMO_FINDINGS), "demo-corpus")
        source = "demo-corpus"
    else:  # pragma: no cover - argparse guarantees one of the branches above
        raise AssertionError("unreachable")

    report = build_explanation_consistency_report(findings, source=source, accessible_public_ids=accessible)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"explanation consistency report: {report['findings_checked']} findings, "
        f"{report['consistent_count']} consistent, {report['inconsistent_count']} inconsistent "
        f"-> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
