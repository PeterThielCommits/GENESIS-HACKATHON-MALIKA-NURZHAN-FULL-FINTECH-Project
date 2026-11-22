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

Precedence when several conditions hold: 4 > 3 > 2 > 1 > 5 > 0.
A check that exits 0 but skipped a *critical* test is reported as SKIPPED
(never PASS) and forces exit 5, per TZ §23.3 ("Cannot return 0 if a critical
check was SKIPPED"). Skips whose reason names an optional extra (e.g.
Hypothesis, TZ §20.2) are recorded under ``optional_checks.skipped`` and do
not force exit 5.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
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

# TZ §23.5 required artifacts for a complete full-mode run (plus the Phase 11
# robustness report and the Phase 14 report index / HTML synthesized by
# judge/report.py). Missing any of these in full mode means the suite is
# incomplete (exit 5), never a silent PASS.
REQUIRED_FULL_ARTIFACTS: tuple[str, ...] = (
    "verify_summary.json",
    "verify_summary.txt",
    "rubric_matrix.csv",
    "episode_matrix.csv",
    "generator_report.json",
    "invariants_report.json",
    "verifier_report_index.json",
    "reward_strategy_report.json",
    "shortcut_audit.json",
    "canary_fuzz_report.json",
    "mutation_test_report.json",
    "metamorphic_report.json",
    "replay_report.json",
    "performance_report.json",
    "dependency_report.json",
    "limitations_snapshot.md",
    "robustness_report.json",
    "report.html",
    "report_index.json",
)

# Skip reasons that name an optional extra (TZ §20.2 / §22.2), or a deliberate
# bootstrap/positional skip whose authoritative check runs elsewhere. Any other
# skipped test is critical: the suite cannot claim PASS for that check.
#
# "evidence artifacts not generated yet" comes from tests/judge/test_doc_claims.py:
# inside RC-001 no artifact exists yet by construction, so those tests can only
# prove the checker's mechanisms. judge/verify.py runs the authoritative
# documentation gate AFTER all artifacts are written (/ _run_doc_claims), so this
# positional skip does not weaken the gate — it moves it to the only correct place.
_OPTIONAL_SKIP_RE = re.compile(
    # "trajectories not generated yet" comes from tests/judge/test_replay_all.py:
    # the committed trajectory log is not part of the Docker image or the offline
    # container (the trajectories tmpfs is deliberately empty so a run proves it
    # produces its own outputs). The authoritative TZ 16.4 check is
    # `make replay-all`, which reads the log where it exists.
    r"hypothesis|extra not installed|optional|"
    r"evidence artifacts not generated yet|trajectories not generated yet",
    re.IGNORECASE,
)
_SKIP_LINE_RE = re.compile(r"\.\.\.\s*skipped\s+'([^']*)'")


def parse_skipped_counts(output: str) -> tuple[int, int]:
    """Split unittest skip lines into (optional_skipped, critical_skipped).

    Parses the full (untruncated) combined stdout+stderr. If the output
    reports ``skipped=N`` but no per-test skip lines are visible (e.g. the
    runner was not verbose), the skips are treated as critical — the
    conservative choice, since PASS must never hide an unknown skip.
    """
    optional = 0
    critical = 0
    seen = 0
    for m in _SKIP_LINE_RE.finditer(output):
        seen += 1
        if _OPTIONAL_SKIP_RE.search(m.group(1)):
            optional += 1
        else:
            critical += 1
    if seen == 0:
        m = re.search(r"skipped=(\d+)", output)
        if m:
            critical = int(m.group(1))
    return optional, critical


def classify_check(
    code: int, is_blocker: bool, optional_skipped: int, critical_skipped: int
) -> tuple[str, str, bool, bool, bool]:
    """Map a subprocess exit code to (status, reason, release_blocked, resource_err, incomplete).

    Pure function (no I/O) so the exit-code contract is unit-testable.
    """
    if code == 0:
        if critical_skipped > 0:
            return (
                "SKIPPED",
                f"exit 0 but {critical_skipped} critical test(s) skipped; suite incomplete",
                False,
                False,
                True,
            )
        return ("PASS", "", False, False, False)
    if code == 4:
        return ("BLOCKED", "release blocker (exit 4)", True, False, False)
    if code == 2:
        return ("FAIL", "configuration/contract error (exit 2)", False, False, False)
    if code == 5:
        return ("BLOCKED", "suite incomplete / required dependency missing (exit 5)", False, False, True)
    if code == 3:
        return ("FAIL", "resource/environment error (exit 3)", False, True, False)
    # Any other non-zero exit is a check failure; blocker checks escalate to
    # a release blocker (TZ §23.3 exit 4).
    reason = f"exit {code}"
    return ("FAIL", reason, bool(is_blocker), False, False)


def load_rubric_map(path: Path = RUBRIC_MAP_PATH) -> tuple[dict[str, Any] | None, str | None]:
    """Load and minimally validate the rubric map. Returns (data, error)."""
    if not path.is_file():
        return None, f"missing {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"malformed rubric map {path}: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get("checks"), list) or not data["checks"]:
        return None, f"rubric map {path} must contain a non-empty 'checks' list"
    return data, None


def check_artifact_completeness(report_dir: Path = REPORT_DIR) -> list[str]:
    """Return the required full-mode artifacts missing from ``report_dir``."""
    return [name for name in REQUIRED_FULL_ARTIFACTS if not (report_dir / name).is_file()]


def _run_doc_claims() -> tuple[int | None, str]:
    """Run the documentation-claim gate (Phase 15) and return (rc, short detail).

    ``None`` as return code means the checker is absent or crashed, which makes
    the suite incomplete rather than passing.
    """
    script = REPO_ROOT / "tools" / "verify_doc_claims.py"
    if not script.is_file():
        return (None, "tools/verify_doc_claims.py not found")
    try:
        code, output, _dur, _opt, _crit = _run_cmd([sys.executable, str(script)])
    except Exception as exc:  # pragma: no cover - defensive
        return (None, f"checker crashed: {exc}")
    lines = [ln.strip() for ln in output.strip().splitlines() if ln.strip()]
    summary = lines[0] if lines else "no output"
    detail = " | ".join(ln for ln in lines if "[" in ln)[:300] or summary[:300]
    return (code, detail)


def _run_cmd(cmd: list[str]) -> tuple[int, str, float, int, int]:
    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=600)
    dur = time.monotonic() - t0
    out = (proc.stdout or "") + (proc.stderr or "")
    optional_skipped, critical_skipped = parse_skipped_counts(out)
    return proc.returncode, out[-8000:], dur, optional_skipped, critical_skipped


def _write_rubric_matrix_csv(results: list[dict[str, Any]], rubric_by_id: dict[str, Any]) -> None:
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

    rubric_data, rubric_err = load_rubric_map()
    if rubric_data is None:
        print(f"verify: configuration error: {rubric_err}", file=sys.stderr)
        return 2
    rubric_by_id = {c["check_id"]: c for c in rubric_data.get("checks", []) if isinstance(c, dict) and "check_id" in c}

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    active_checks = [c for c in ALL_CHECKS if (c[4] if args.core else True)]

    results: list[dict[str, Any]] = []
    failed_req = 0
    release_blocked = False
    resource_err = False
    config_err = False
    incomplete = False
    total_optional_skipped = 0
    total_critical_skipped = 0
    suite_start = time.monotonic()

    for check_id, req_id, cmd, required, _core_only, is_blocker, artifact_rel in active_checks:
        try:
            code, output, dur, opt_skip, crit_skip = _run_cmd(cmd)
            status, reason, blocked_flag, resource_flag, incomplete_flag = classify_check(
                code, is_blocker, opt_skip, crit_skip
            )
            if status != "PASS" and required:
                failed_req += 1
            if blocked_flag:
                release_blocked = True
            if resource_flag:
                resource_err = True
            if incomplete_flag:
                incomplete = True
            if code == 2:
                config_err = True
            total_optional_skipped += opt_skip
            total_critical_skipped += crit_skip
        except subprocess.TimeoutExpired:
            code, output, dur, status, reason = 3, "TIMEOUT (>600s)", 600.0, "FAIL", "timeout (>600s)"
            opt_skip = crit_skip = 0
            failed_req += 1 if required else 0
            resource_err = True
        except Exception as exc:
            code, output, dur, status, reason = 3, f"ENV ERROR: {exc}", 0.0, "BLOCKED", f"environment error: {exc}"
            opt_skip = crit_skip = 0
            failed_req += 1 if required else 0
            resource_err = True

        rm = rubric_by_id.get(check_id, {})
        results.append(
            {
                "check_id": check_id,
                "req_id": req_id,
                "rubric_item": rm.get("rubric_item", req_id),
                "command": " ".join(cmd),
                "status": status,
                "reason": reason,
                "required": required,
                "release_blocker": is_blocker,
                "exit_code": code,
                "duration_s": round(dur, 3),
                "skipped_optional": opt_skip,
                "skipped_critical": crit_skip,
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
    _write_rubric_matrix_csv(results, rubric_by_id)

    # ---- TZ §23.5 report synthesis, ordered so a clean checkout works -------
    # ``judge/report.py`` consumes verify_summary.json, so the summary must be
    # written FIRST and re-written AFTER the HTML/index exist. Otherwise a
    # clean checkout (empty artifacts/reports/latest/) would fail the report
    # step even though every gate passed — that would break EXIT GATE 14.
    REPORT_PRODUCTS: tuple[str, ...] = ("report.html", "report_index.json")
    report_rc = 0
    missing_artifacts: list[str] = []
    artifact_schema_errors: list[str] = []

    if not args.core:
        from judge import schemas as schemas_mod

        # Advisory only: before this run's summary/report exist, completeness is
        # necessarily incomplete (verify_summary.json, report.html and
        # report_index.json are written below). The FINAL completeness pass
        # after judge/report.py is the single authority for exit 5, so nothing
        # here may set ``incomplete``.
        _pre_missing = [m for m in check_artifact_completeness() if m not in REPORT_PRODUCTS]
        if _pre_missing:
            print(
                "verify: artifacts pending synthesis before report step: "
                + ", ".join(_pre_missing)
            )

    def _write_summary() -> dict[str, Any]:
        passed = sum(1 for r in results if r["status"] == "PASS")
        blocked = sum(1 for r in results if r["status"] == "BLOCKED")
        skipped = sum(1 for r in results if r["status"] == "SKIPPED")
        status = "PASS" if (failed_req == 0 and not incomplete) else ("BLOCKED" if release_blocked else "FAIL")
        artifacts = sorted(
            f"artifacts/reports/latest/{p.name}" for p in REPORT_DIR.iterdir() if p.is_file()
        )
        for name in ("verify_summary.json", "verify_summary.txt"):
            rel = f"artifacts/reports/latest/{name}"
            if rel not in artifacts:
                artifacts.append(rel)
        artifacts.sort()
        doc: dict[str, Any] = {
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
            "status": status,
            "total_duration_s": total_dur,
            "official_score_claimed": False,
            "internal_pass_rate_pct": round((100.0 * passed) / max(1, len(results)), 2),
            "required_checks": {
                "total": len(results),
                "passed": passed,
                "failed": failed_req,
                "blocked": blocked,
                "skipped": skipped,
            },
            "optional_checks": {
                "passed": sum(1 for r in results if r["status"] == "PASS" and r["skipped_optional"] > 0),
                "skipped": total_optional_skipped,
                "critical_skipped": total_critical_skipped,
            },
            "missing_artifacts": missing_artifacts,
            "artifact_schema_errors": artifact_schema_errors,
            "checks": results,
            "artifacts": artifacts,
        }
        (REPORT_DIR / "verify_summary.json").write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (REPORT_DIR / "verify_summary.txt").write_text(
            f"TwinLedger Judge Kit ({doc['mode']}): {status} "
            f"({passed}/{len(results)} checks passed in {total_dur}s)\n"
            + "\n".join(
                f"  [{r['status']}] {r['check_id']} {r['req_id']} ({r['duration_s']}s) -> {r['artifact']}"
                for r in results
            )
            + ("\nMissing artifacts: " + ", ".join(missing_artifacts) if missing_artifacts else "")
            + ("\nArtifact contract errors: " + "; ".join(artifact_schema_errors[:10]) if artifact_schema_errors else "")
            + "\nDisclaimer: Internal TwinLedger verification pass rate ONLY; NOT an official organiser jury score.\n",
            encoding="utf-8",
        )
        return doc

    summary = _write_summary()  # phase A: unblocks judge/report.py on a clean clone

    if not args.core:
        from judge import report as report_mod

        report_rc = report_mod.main()
        if report_rc == 4:
            release_blocked = True
        elif report_rc != 0:
            incomplete = True

        missing_artifacts = check_artifact_completeness()
        if missing_artifacts:
            incomplete = True
        # Final pass: every JSON report (including this run's summary and the
        # freshly synthesized index) must honour the TZ §23.5 envelope.
        artifact_schema_errors = schemas_mod.validate_report_dir_envelopes(REPORT_DIR)
        index_path = REPORT_DIR / "report_index.json"
        if index_path.is_file():
            try:
                index_doc = json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                artifact_schema_errors.append(f"report_index.json: unparseable JSON: {exc}")
            else:
                artifact_schema_errors.extend(schemas_mod.validate_report_index(index_doc))
        if artifact_schema_errors:
            config_err = True
            print("verify: artifact contract errors (TZ §23.5):")
            for err in artifact_schema_errors[:20]:
                print(f"  - {err}")

        # TZ §24 Task 15.5/15.6 (REQ-DOC-001..003): documentation must match the
        # evidence that now exists. This is the authoritative position — the
        # doc-claim tests inside RC-001 can only bootstrap-report SKIPPED, because
        # at that moment no artifact has been produced yet.
        doc_claims_rc, doc_claims_out = _run_doc_claims()
        if doc_claims_rc == 0:
            print("verify: documentation claims PASS (docs match measured artifacts)")
        elif doc_claims_rc is None:
            incomplete = True
            print(f"verify: documentation claim check unavailable: {doc_claims_out}")
        else:
            failed_req += 1
            print(f"verify: documentation claims FAILED (exit {doc_claims_rc}): {doc_claims_out}")
        summary = _write_summary()  # phase B: final status, artifacts and errors

    print(f"verify: {summary['status']} ({total_dur}s) — artifacts/reports/latest/verify_summary.json")
    if failed_req == 0 and not incomplete and report_rc == 0:
        return 0
    if release_blocked:
        return 4
    if resource_err:
        return 3
    if config_err:
        return 2
    if failed_req > 0:
        return 1
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
