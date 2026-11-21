#!/usr/bin/env python3
"""Judge Kit verification CLI (TZ 23).

Runs required checks and writes machine-readable reports to
``artifacts/reports/latest/``. Exit codes (TZ 23.3):
  0 all required PASS (optional SKIPPED allowed, explicitly listed)
  1 one or more required FAIL
  2 configuration/contract error
  3 resource/environment error
  4 release blocker
  5 test suite incomplete / required dependency missing

Phase 1 scope: contracts, canonical JSON, import boundaries, configs.
Later phases extend CHECKS; this file must never silently skip a
required check (REQ-JUDGE-003).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "artifacts" / "reports" / "latest"

# (check_id, req_id, command, required)
CHECKS: list[tuple[str, str, list[str], bool]] = [
    ("RC-001", "REQ-CONTRACT-001", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"], True),
    ("RC-002", "REQ-ARC-001", [sys.executable, "tools/check_import_boundaries.py"], True),
    ("RC-003", "REQ-CONTRACT-010", [sys.executable, "-m", "unittest", "tests.unit.test_canonical", "-v"], True),
    ("RC-004", "OFFICIAL-2026-11-20", [sys.executable, "-m", "unittest", "discover", "-s", "tests/official", "-t", ".", "-v"], True),
    ("RC-005", "REQ-SEAL-030", [sys.executable, "-m", "harness.replay", "--verify-suite"], True),
]


def _run(cmd: list[str]) -> tuple[int, str, float]:
    start = time.monotonic()
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
    dur = time.monotonic() - start
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out[-8000:], dur


def main() -> int:
    parser = argparse.ArgumentParser(description="TwinLedger verify")
    parser.add_argument("--core", action="store_true", help="critical core checks only")
    parser.add_argument("--full", action="store_true", help="full rubricator")
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    failed = 0
    for check_id, req_id, cmd, required in CHECKS:
        try:
            code, output, dur = _run(cmd)
            status = "PASS" if code == 0 else "FAIL"
            if status == "FAIL" and required:
                failed += 1
        except subprocess.TimeoutExpired:
            code, output, dur, status = 3, "TIMEOUT", 600.0, "FAIL"
            failed += 1
        except Exception as exc:  # environment error
            code, output, dur, status = 3, f"ENV ERROR: {exc}", 0.0, "BLOCKED"
            failed += 1
        results.append({
            "check_id": check_id, "req_id": req_id, "command": " ".join(cmd),
            "status": status, "required": required, "exit_code": code,
            "duration_s": round(dur, 3), "output_tail": output[-2000:],
            "artifact": "artifacts/reports/latest/verify_summary.json",
        })
        print(f"[{status}] {check_id} ({req_id}) {' '.join(cmd)}")

    summary = {
        "schema_version": "1.0.0",
        "run_id": f"verify-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "mode": "core" if args.core else "full",
        "status": "PASS" if failed == 0 else "FAIL",
        "official_score_claimed": False,
        "required_checks": {"passed": sum(1 for r in results if r["status"] == "PASS"), "failed": failed, "blocked": 0},
        "optional_checks": {"passed": 0, "skipped": 0},
        "checks": results,
        "artifacts": [
            "artifacts/reports/latest/verify_summary.json",
            *(
                ["artifacts/reports/latest/replay_report.json"]
                if (REPORT_DIR / "replay_report.json").is_file()
                else []
            ),
        ],
    }
    (REPORT_DIR / "verify_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (REPORT_DIR / "verify_summary.txt").write_text(
        f"TwinLedger verify ({summary['mode']}): {summary['status']}\n"
        + "\n".join(f"  [{r['status']}] {r['check_id']} {r['req_id']} — {' '.join(r['command'].split()[:4])}" for r in results)
        + "\nNote: internal verification status only; NOT an official organiser score.\n",
        encoding="utf-8",
    )
    print(f"verify: {summary['status']} — artifacts/reports/latest/verify_summary.json")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
