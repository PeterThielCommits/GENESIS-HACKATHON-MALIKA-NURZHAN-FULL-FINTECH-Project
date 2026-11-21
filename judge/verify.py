#!/usr/bin/env python3
"""Judge Kit Verification CLI (Phases 14–16 — Master TZ §23.1–23.6).

Runs the full 12-gate TwinLedger rubricator (`RC-001..RC-012`) and writes
machine-readable evidence artifacts to ``artifacts/reports/latest/``.

Exit codes (TZ §23.3):
  0 all required checks PASS (optional SKIPPED explicitly listed)
  1 one or more required checks FAIL
  2 configuration/contract error
  3 resource/environment error
  4 release blocker (canary leakage, replay tamper, invalid truth)
  5 test suite incomplete / required dependency missing
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.canonical import sha256_hex

REPORT_DIR = REPO_ROOT / "artifacts" / "reports" / "latest"
RUBRIC_MAP_PATH = REPO_ROOT / "judge" / "rubric_map.json"

# (check_id, req_id, cmd, required, core_gate, is_release_blocker, primary_artifact)
ALL_CHECKS: list[tuple[str, str, list[str], bool, bool, bool, str]] = [
    ("RC-001", "REQ-CONTRACT-001", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"], True, True, False, "artifacts/reports/latest/verify_summary.json"),
    ("RC-002", "REQ-ARC-001", [sys.executable, "tools/check_import_boundaries.py"], True, True, True, "artifacts/reports/latest/verify_summary.json"),
    ("RC-003", "REQ-CONTRACT-010", [sys.executable, "-m", "unittest", "tests.unit.test_property", "-v"], True, True, False, "artifacts/reports/latest/verify_summary.json"),
    ("RC-004", "OFFICIAL-2026-11-20", [sys.executable, "-m", "unittest", "discover", "-s", "tests/official", "-t", ".", "-v"], True, True, True, "artifacts/reports/latest/verify_summary.json"),
    ("RC-005", "REQ-SEAL-030", [sys.executable, "-m", "harness.replay", "--verify-suite"], True, True, True, "artifacts/reports/latest/replay_report.json"),
    ("RC-006", "REQ-NLP-004", [sys.executable, "judge/robustness_audit.py"], True, False, False, "artifacts/reports/latest/robustness_report.json"),
    ("RC-007", "REQ-ARENA-001", [sys.executable, "arena/autohacker.py"], True, False, False, "artifacts/reports/latest/reward_strategy_report.json"),
    ("RC-008", "REQ-SHORTCUT-001", [sys.executable, "judge/shortcut_audit.py"], True, False, False, "artifacts/reports/latest/shortcut_audit.json"),
    ("RC-009", "REQ-LEAK-001", [sys.executable, "judge/canary_fuzzer.py"], True, True, True, "artifacts/reports/latest/canary_fuzz_report.json"),
    ("RC-010", "REQ-TEST-002", [sys.executable, "judge/mutation_suite.py"], True, False, False, "artifacts/reports/latest/mutation_test_report.json"),
    ("RC-011", "REQ-TEST-004", [sys.executable, "metamorphic/suite.py"], True, False, False, "artifacts/reports/latest/metamorphic_report.json"),
    ("RC-012", "REQ-OPS-001", [sys.executable, "judge/performance_and_deps.py"], True, False, False, "artifacts/reports/latest/performance_report.json"),
]


def _run_cmd(cmd: list[str]) -> tuple[int, str, float]:
    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
    dur = time.monotonic() - t0
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out[-8000:], dur


def _write_rubric_matrix_csv(results: list[dict[str, Any]]) -> None:
    rubric_raw = json.loads(RUBRIC_MAP_PATH.read_text(encoding="utf-8")) if RUBRIC_MAP_PATH.is_file() else {"checks": []}
    rubric_by_id = {c["check_id"]: c for c in rubric_raw.get("checks", [])}
    csv_path = REPORT_DIR / "rubric_matrix.csv"
    fields = ["check_id", "req_id", "rubric_item", "provisional", "required", "status", "duration_s", "artifact"]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in results:
            rm = rubric_by_id.get(r["check_id"], {})
            w.writerow(
                {
                    "check_id": r["check_id"],
                    "req_id": r["req_id"],
                    "rubric_item": rm.get("rubric_item", r["req_id"]),
                    "provisional": rm.get("provisional", True),
                    "required": r["required"],
                    "status": r["status"],
                    "duration_s": r["duration_s"],
                    "artifact": r["artifact"],
                }
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger Judge Kit verification suite")
    parser.add_argument("--core", action="store_true", help="Run critical core & release-blocker checks only")
    parser.add_argument("--full", action="store_true", help="Run full 12-gate rubricator & synthesize all 17 reports")
    args = parser.parse_args(argv)

    if not RUBRIC_MAP_PATH.is_file():
        print("verify: missing judge/rubric_map.json", file=sys.stderr)
        return 2

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    active_checks = [c for c in ALL_CHECKS if (c[4] if args.core else True)]

    results: list[dict[str, Any]] = []
    failed_req = 0
    release_blocked = False
    resource_err = False
    suite_start = time.monotonic()

    for check_id, req_id, cmd, required, _core_only, is_blocker, artifact_rel in active_checks:
        try:
            code, output, dur = _run_cmd(cmd)
            if code == 0:
                status = "PASS"
            elif code == 4 or is_blocker:
                status = "BLOCKED" if code == 4 else "FAIL"
                failed_req += 1 if required else 0
                if is_blocker:
                    release_blocked = True
            elif code == 3:
                status = "FAIL"
                failed_req += 1 if required else 0
                resource_err = True
            else:
                status = "FAIL"
                failed_req += 1 if required else 0
        except subprocess.TimeoutExpired:
            code, output, dur, status = 3, "TIMEOUT (>600s)", 600.0, "FAIL"
            failed_req += 1 if required else 0
            resource_err = True
        except Exception as exc:
            code, output, dur, status = 3, f"ENV ERROR: {exc}", 0.0, "BLOCKED"
            failed_req += 1 if required else 0
            resource_err = True

        results.append(
            {
                "check_id": check_id,
                "req_id": req_id,
                "command": " ".join(cmd),
                "status": status,
                "required": required,
                "release_blocker": is_blocker,
                "exit_code": code,
                "duration_s": round(dur, 3),
                "output_tail": output[-1500:],
                "artifact": artifact_rel,
            }
        )
        print(f"[{status}] {check_id} ({req_id}) ({dur:.2f}s) -> {artifact_rel}")
        if code != 0:
            tail_flat = " | ".join(line.strip() for line in output.strip().splitlines()[-8:] if line.strip())
            print(f"  detail ({check_id}): {tail_flat[-600:]}")
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(f"::error title={check_id} ({req_id}) {status}::{tail_flat[-500:]}")

    total_dur = round(time.monotonic() - suite_start, 3)
    _write_rubric_matrix_csv(results)

    overall_status = "PASS" if failed_req == 0 else ("BLOCKED" if release_blocked else "FAIL")
    passed_count = sum(1 for r in results if r["status"] == "PASS")
    blocked_count = sum(1 for r in results if r["status"] == "BLOCKED")

    existing_artifacts = sorted(
        f"artifacts/reports/latest/{p.name}"
        for p in REPORT_DIR.iterdir()
        if p.is_file()
    )
    if "artifacts/reports/latest/verify_summary.json" not in existing_artifacts:
        existing_artifacts.append("artifacts/reports/latest/verify_summary.json")
    if "artifacts/reports/latest/verify_summary.txt" not in existing_artifacts:
        existing_artifacts.append("artifacts/reports/latest/verify_summary.txt")
    existing_artifacts.sort()

    summary = {
        "schema_version": "1.0.0",
        "report_type": "verify_summary",
        "code_version": "twinledger@1.0.0",
        "config_hash": sha256_hex({"mode": "core" if args.core else "full", "checks": [c[0] for c in active_checks]}),
        "run_id": f"verify-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "command": f"python3 judge/verify.py {'--core' if args.core else '--full'}",
        "mode": "core" if args.core else "full",
        "status": overall_status,
        "total_duration_s": total_dur,
        "official_score_claimed": False,
        "internal_pass_rate_pct": round((100.0 * passed_count) / max(1, len(results)), 2),
        "required_checks": {
            "total": len(results),
            "passed": passed_count,
            "failed": failed_req,
            "blocked": blocked_count,
        },
        "optional_checks": {"passed": 0, "skipped": 0},
        "checks": results,
        "artifacts": existing_artifacts,
    }
    (REPORT_DIR / "verify_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (REPORT_DIR / "verify_summary.txt").write_text(
        f"TwinLedger Judge Kit ({summary['mode']}): {summary['status']} "
        f"({passed_count}/{len(results)} checks passed in {total_dur}s)\n"
        + "\n".join(
            f"  [{r['status']}] {r['check_id']} {r['req_id']} ({r['duration_s']}s) -> {r['artifact']}"
            for r in results
        )
        + "\nDisclaimer: Internal TwinLedger verification pass rate ONLY; NOT an official organiser jury score.\n",
        encoding="utf-8",
    )

    # In full mode, automatically synthesize report_index.json & static offline report.html
    if not args.core:
        from judge import report as report_mod

        report_mod.main()

    print(f"verify: {summary['status']} ({total_dur}s) — artifacts/reports/latest/verify_summary.json")
    if failed_req == 0:
        return 0
    if release_blocked:
        return 4
    if resource_err:
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
