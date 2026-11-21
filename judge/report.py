#!/usr/bin/env python3
"""Aggregated report writer (TZ 23.5). Phase 1: verify summary only.

Later phases add episode_matrix, generator/invariants/verifier/reward/
shortcut/canary/mutation/metamorphic/replay/performance reports.
Stdlib-only; no network, no CDN.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "artifacts" / "reports" / "latest"


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = REPORT_DIR / "verify_summary.json"
    if not summary_path.exists():
        print("report: no verify_summary.json found — run `make verify` first.")
        return 5
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    (REPORT_DIR / "report_index.json").write_text(
        json.dumps({"schema_version": "1.0.0", "verify_status": summary.get("status"),
                    "artifacts": ["verify_summary.json", "verify_summary.txt", "report_index.json"]},
                   indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("report: artifacts/reports/latest/report_index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
