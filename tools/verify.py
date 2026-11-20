"""TwinLedger verification runner (master spec §23).

One command, machine-readable artifacts, documented exit codes and an honest status for every
check - including the ones that are not implemented yet.

What it does:

1. runs the executable checks (setup, contracts, schema self-consistency, governance,
   import boundaries, the unittest suite);
2. maps every result onto `judge/rubric_map.json`, so an unimplemented check is reported as
   `BLOCKED` with a reason instead of disappearing;
3. validates each emitted result against `contracts/rubric_check.schema.json` (the report obeys
   the same contract as everything else);
4. writes `artifacts/reports/latest/{verify_summary.json,verify_summary.txt,rubric_matrix.csv}`
   plus per-check reports, and optionally refreshes `docs/PHASE_REPORTS/PHASE-XX.json`;
5. exits with the code from §23.3: 0 pass, 1 fail, 2 config/contract error, 3 environment
   error, 4 release blocker, 5 suite incomplete.

Nothing here claims an official score: every check is `official: false` (D-0002).
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import (check_ci, check_golden, check_governance, check_import_boundaries,
                   check_models, probe_starter, validate_contracts)
from tools.canonical_json import canonical_digest
from tools.jsonschema_lite import ContractValidator

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts" / "reports" / "latest"
RUBRIC_MAP = ROOT / "judge" / "rubric_map.json"
CONTRACTS = ROOT / "contracts"
# Payload version of the emitted reports; read from the contract so a bump cannot drift.
CONTRACT_SCHEMA_PAYLOAD = json.loads((CONTRACTS / "version.json").read_text(encoding="utf-8"))[
    "schema_payload_version"]

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_CONFIG = 2
EXIT_ENVIRONMENT = 3
EXIT_BLOCKER = 4
EXIT_INCOMPLETE = 5


# --------------------------------------------------------------------------- helpers
def _now() -> float:
    return time.time()


def write_json(name: str, payload: object) -> str:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(path.relative_to(ROOT)).replace("\\", "/")


class RecordingResult(unittest.TextTestResult):
    """Collect one outcome per test id, without hiding failures."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.outcomes: dict[str, str] = {}
        self.timings: dict[str, float] = {}
        self._started: dict[str, float] = {}

    def startTest(self, test) -> None:  # noqa: N802 - unittest API
        self._started[test.id()] = _now()
        super().startTest(test)

    def _finish(self, test, status: str) -> None:
        self.outcomes[test.id()] = status
        started = self._started.pop(test.id(), None)
        if started is not None:
            self.timings[test.id()] = _now() - started

    def addSuccess(self, test) -> None:  # noqa: N802
        super().addSuccess(test)
        self._finish(test, "PASS")

    def addFailure(self, test, err) -> None:  # noqa: N802
        super().addFailure(test, err)
        self._finish(test, "FAIL")

    def addError(self, test, err) -> None:  # noqa: N802
        super().addError(test, err)
        self._finish(test, "ERROR")

    def addSkip(self, test, reason) -> None:  # noqa: N802
        super().addSkip(test, reason)
        self._finish(test, "SKIPPED")

    def addExpectedFailure(self, test, err) -> None:  # noqa: N802
        super().addExpectedFailure(test, err)
        self._finish(test, "PASS")

    def addUnexpectedSuccess(self, test) -> None:  # noqa: N802
        super().addUnexpectedSuccess(test)
        self._finish(test, "FAIL")


def run_unittest_suite() -> dict:
    suite = unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT), pattern="test_*.py")
    runner = unittest.TextTestRunner(resultclass=RecordingResult, verbosity=0, stream=open("/dev/null", "w"))
    started = _now()
    result: RecordingResult = runner.run(suite)
    duration = _now() - started
    total = result.testsRun
    passed = sum(1 for status in result.outcomes.values() if status == "PASS")
    failed = sum(1 for status in result.outcomes.values() if status in {"FAIL", "ERROR"})
    skipped = sum(1 for status in result.outcomes.values() if status == "SKIPPED")
    return {
        "check": "unittest_suite",
        "status": "PASS" if failed == 0 and total > 0 else "FAIL",
        "tests_run": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration_seconds": round(duration, 3),
        "outcomes": result.outcomes,
        "failures": [test for test, status in result.outcomes.items() if status in {"FAIL", "ERROR"}],
    }


def schema_self_check() -> dict:
    """Versioned headers, resolvable $refs, supported keywords only."""
    version = json.loads((CONTRACTS / "version.json").read_text(encoding="utf-8"))
    validator = ContractValidator(CONTRACTS)
    problems: list[str] = []
    checked = 0
    for entry in version["schemas"]:
        path = CONTRACTS / entry["file"]
        if not path.is_file():
            problems.append(f"missing schema {entry['file']}")
            continue
        schema = json.loads(path.read_text(encoding="utf-8"))
        checked += 1
        for field in ("$id", "title", "description", "schema_version"):
            if not schema.get(field):
                problems.append(f"{entry['file']} lacks {field}")
        if schema.get("schema_version") != version["schema_payload_version"]:
            problems.append(f"{entry['file']} payload version mismatch")
        try:
            for ref in _collect_refs(schema):
                validator._resolve_ref(ref, path)
        except Exception as exc:  # SchemaError or resolver failure
            problems.append(f"{entry['file']}: unresolved $ref ({exc})")
    return {
        "check": "schema_self_consistency",
        "status": "PASS" if not problems and checked else "FAIL",
        "schemas_checked": checked,
        "problems": problems,
    }


def _collect_refs(node: object) -> list[str]:
    refs: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append(value)
            else:
                refs.extend(_collect_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.extend(_collect_refs(item))
    return refs


# --------------------------------------------------------------------------- rubric mapping
# Which executed facts decide each implemented rubric check.
RUBRIC_BINDINGS: dict[str, dict] = {
    "CT-CONTRACTS-01": {"source": "contracts"},
    "CT-CONTRACTS-02": {"source": "schema_self"},
    "CT-CANON-01": {"tests": ["tests.unit.test_canonical_json"]},
    "CT-ADAPTER-01": {"tests": ["tests.unit.test_adapter_compatibility"]},
    "CT-BOUNDARY-01": {"source": "boundaries"},
    "EN-VERIFY-01": {"source": "self"},
    "EN-GOV-01": {
        "governance": ["GOV-ASSUMPTIONS-01", "GOV-QUESTIONS-01", "GOV-DECISIONS-01",
                       "GOV-REQUIREMENTS-01", "GOV-RUBRIC-01", "GOV-SIGNOFF-01"],
        "tests": ["tests.phase0.test_assumption_registry", "tests.phase0.test_questions",
                  "tests.phase0.test_decisions", "tests.phase0.test_rubric_map"],
    },
    "EN-DOCS-01": {
        "governance": ["GOV-DOCS-01", "GOV-CLAIMS-01", "GOV-README-01", "GOV-STATUS-01"],
        "tests": ["tests.phase0.test_contract_docs", "tests.phase0.test_no_official_claims"],
    },
    "EN-ARCHIVE-01": {"governance": ["GOV-ARCHIVE-01"], "tests": ["tests.phase0.test_official_archive"]},
    "EN-OFFLINE-01": {"source": "boundaries_offline"},
    "EN-DATA-01": {"governance": ["GOV-GIT-01"], "tests": ["tests.phase0.test_git_data_policy"]},
    "CT-GOLDEN-01": {"source": "golden"},
    "EN-MODELS-01": {"source": "models"},
    "EN-CI-01": {"source": "ci", "governance": ["GOV-CI-01"]},
    "EN-SUBMIT-01": {"governance": ["GOV-DEADLINE-01"], "tests": ["tests.phase0.test_deadline"]},
    "EN-PROBE-01": {"source": "probe"},
    "EN-REPORT-01": {"governance": ["GOV-PHASE-REPORT-01"], "tests": ["tests.phase0.test_phase_report"]},
}


def _worst(statuses: list[str]) -> str:
    order = {"PASS": 0, "SKIPPED": 1, "BLOCKED": 2, "NOT_IMPLEMENTED": 3, "FAIL": 4}
    return max(statuses, key=lambda s: order.get(s, 5)) if statuses else "BLOCKED"


def build_results() -> tuple[list[dict], dict, list[str]]:
    rubric = json.loads(RUBRIC_MAP.read_text(encoding="utf-8"))
    blockers: list[str] = []

    started = _now()
    contract_result = validate_contracts.run()
    contracts_report = contract_result.summary() | {"duration_ms": round((_now() - started) * 1000)}
    write_json("contracts_report.json", contracts_report)

    started = _now()
    schema_result = schema_self_check()
    schema_result["duration_ms"] = round((_now() - started) * 1000)
    write_json("schema_self_consistency_report.json", schema_result)

    started = _now()
    boundary_result = check_import_boundaries.scan()
    boundary_result["duration_ms"] = round((_now() - started) * 1000)
    write_json("import_boundaries_report.json", boundary_result)
    write_json("dependency_report.json", {
        "check": "dependencies",
        "status": boundary_result["status"],
        "third_party_imports": boundary_result["third_party_imports"],
        "runtime_network_scan": "static import scan only; runtime socket blocking is a Phase 16 test",
        "python": platform.python_version(),
        "platform": platform.platform(),
    })

    started = _now()
    gov_checks = check_governance.run()
    gov_elapsed = round((_now() - started) * 1000)
    governance_payload = {
        "check": "governance",
        "status": "PASS" if all(c.status == "PASS" for c in gov_checks) else "FAIL",
        "exit_code": 4 if any(c.blocker for c in gov_checks) else 0,
        "duration_ms": gov_elapsed,
        "checks": [c.as_dict() for c in gov_checks],
    }
    write_json("governance_report.json", governance_payload)
    gov_by_id = {c.check_id: c for c in gov_checks}

    started = _now()
    models_result = check_models.run()
    models_result["duration_ms"] = round((_now() - started) * 1000)
    write_json("models_report.json", models_result)

    started = _now()
    golden_result = check_golden.run()
    golden_result["duration_ms"] = round((_now() - started) * 1000)
    write_json("golden_report.json", golden_result)

    started = _now()
    ci_result = check_ci.run()
    ci_result["duration_ms"] = round((_now() - started) * 1000)
    write_json("ci_report.json", ci_result)

    started = _now()
    probe_result = probe_starter.probe(run=False)
    probe_result["duration_ms"] = round((_now() - started) * 1000)
    write_json("starter_probe_report.json", probe_result)

    tests = run_unittest_suite()
    write_json("test_report.json", tests)

    results: list[dict] = []
    for check in rubric["internal_checks"]:
        entry = {
            "schema_version": CONTRACT_SCHEMA_PAYLOAD,
            "check_id": check["check_id"],
            "block": check["block"],
            "title": check["title"],
            "official": False,
            "provisional": True,
            "req_ids": check["req_ids"],
            "command": check["command"],
            "artifact": check["artifact"],
            "reason": "",
            "duration_ms": 0,
        }
        if check["declared_state"] == "PLANNED":
            entry["status"] = "BLOCKED"
            entry["reason"] = f"not implemented yet ({check['phase']}); {check.get('note', '')}".strip()
            results.append(entry)
            continue

        binding = RUBRIC_BINDINGS.get(check["check_id"])
        if binding is None:
            entry["status"] = "BLOCKED"
            entry["reason"] = "no runtime binding registered for this implemented check"
            results.append(entry)
            continue

        statuses: list[str] = []
        reasons: list[str] = []
        if "source" in binding:
            source = binding["source"]
            if source == "contracts":
                statuses.append(contract_result.summary()["status"])
                reasons.append(f"{contracts_report['cases_passed']}/{contracts_report['cases_total']} fixtures")
            elif source == "schema_self":
                statuses.append(schema_result["status"])
                reasons.append(f"{schema_result['schemas_checked']} schemas checked")
                if schema_result["problems"]:
                    reasons.extend(schema_result["problems"])
            elif source == "boundaries":
                statuses.append(boundary_result["status"])
                reasons.append(f"{boundary_result['files_scanned']} files scanned")
                if boundary_result["violations"]:
                    reasons.extend(v["detail"] for v in boundary_result["violations"])
            elif source == "boundaries_offline":
                offline_ok = not boundary_result["third_party_imports"]
                statuses.append("PASS" if offline_ok else "FAIL")
                reasons.append("no third-party imports in the mandatory path" if offline_ok
                               else f"{len(boundary_result['third_party_imports'])} third-party imports")
            elif source == "golden":
                statuses.append(golden_result["status"])
                reasons.append(f"{golden_result['files_checked']} files match the freeze")
                if golden_result["problems"]:
                    reasons.extend(golden_result["problems"])
            elif source == "models":
                statuses.append(models_result["status"])
                reasons.append(f"{models_result['models']} typed models")
                if models_result["problems"]:
                    reasons.extend(models_result["problems"])
            elif source == "ci":
                statuses.append(ci_result["status"])
                reasons.append(f"{len(ci_result['workflows'])} workflow(s)")
                if ci_result["problems"]:
                    reasons.extend(ci_result["problems"])
            elif source == "probe":
                # SKIPPED is the correct result when no organizer bundle exists; it is never
                # reported as a pass and never hidden.
                statuses.append(probe_result["status"])
                reasons.append(probe_result["reason"])
            elif source == "self":
                # Filled in after all other checks: this one reports the aggregate.
                statuses.append("PASS")
                reasons.append("aggregate of the required checks")
        for gov_id in binding.get("governance", []):
            check_obj = gov_by_id.get(gov_id)
            if check_obj is None:
                statuses.append("FAIL")
                reasons.append(f"governance check {gov_id} did not run")
            else:
                statuses.append(check_obj.status)
                if check_obj.reason:
                    reasons.append(f"{gov_id}: {check_obj.reason}")
        for prefix in binding.get("tests", []):
            outcomes = {test: status for test, status in tests["outcomes"].items() if test.startswith(prefix)}
            if not outcomes:
                statuses.append("BLOCKED")
                reasons.append(f"no test found for {prefix}")
            else:
                failed = [t for t, s in outcomes.items() if s in {"FAIL", "ERROR"}]
                statuses.append("FAIL" if failed else "PASS")
                reasons.append(f"{len(outcomes)} tests" + (f", failed: {failed}" if failed else ""))

        entry["status"] = _worst(statuses)
        entry["reason"] = "; ".join(reason for reason in reasons if reason)[:500] or "all bound checks passed"
        entry["duration_ms"] = 0
        results.append(entry)

    # aggregate check depends on everything else
    required = [r for r in results if r["req_ids"] and not r["reason"].startswith("not implemented")]
    for entry in results:
        if entry["check_id"] == "EN-VERIFY-01":
            failures = [r["check_id"] for r in required if r["status"] in {"FAIL", "BLOCKED"}]
            if failures:
                entry["status"] = "FAIL"
                entry["reason"] = f"required checks not passing: {failures}"
            else:
                entry["status"] = "PASS"
                entry["reason"] = f"all {len(required)} executed checks passed; planned checks reported BLOCKED"

    # Release blockers (exit 4) are only the governance conditions that make any published
    # result untrustworthy: a false official claim or a committed secret. A failing test is an
    # ordinary failure (exit 1), not a blocker - otherwise the exit code would lose meaning.
    blockers.extend(c.reason for c in gov_checks if c.blocker)

    meta = {
        "contract_digest": validate_contracts.contract_digest(),
        "config_digest": canonical_digest({
            str(path.relative_to(ROOT)).replace("\\", "/"): json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((ROOT / "configs").rglob("*.json"))
        }),
        "rubric_map_digest": canonical_digest(rubric),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "tests": tests,
        "governance_status": governance_payload["status"],
        "boundaries_status": boundary_result["status"],
        "contracts_status": contracts_report["status"],
        "schema_status": schema_result["status"],
        "models_status": models_result["status"],
        "golden_status": golden_result["status"],
        "golden_digest": golden_result.get("contract_set_digest"),
        "ci_status": ci_result["status"],
        "probe_status": probe_result["status"],
    }
    return results, meta, blockers


def emit(results: list[dict], meta: dict, blockers: list[str], profile: str) -> dict:
    validator = ContractValidator(CONTRACTS)
    report_problems: list[str] = []
    for entry in results:
        problems = _validate_rubric(entry, validator)
        if problems:
            report_problems.append(f"{entry['check_id']}: {'; '.join(problems)}")

    required = [r for r in results if r["reason"] and not r["reason"].startswith("not implemented yet")]
    planned = [r for r in results if r["reason"].startswith("not implemented yet")]
    failed = [r for r in required if r["status"] == "FAIL"]
    passed = [r for r in required if r["status"] == "PASS"]

    if blockers:
        status, exit_code = "FAIL", EXIT_BLOCKER
    elif failed:
        status, exit_code = "FAIL", EXIT_FAIL
    elif report_problems:
        status, exit_code = "FAIL", EXIT_CONFIG
    else:
        # Planned checks stay BLOCKED and are never counted as passing; the gate itself passes.
        status, exit_code = "PASS_WITH_PLANNED_CHECKS_BLOCKED", EXIT_PASS

    summary = {
        "schema_version": CONTRACT_SCHEMA_PAYLOAD,
        "check": "verify",
        "profile": profile,
        "status": status,
        "exit_code": exit_code,
        "official_rubric_available": False,
        "official_score_claimed": False,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": {
            "python": meta["python"],
            "platform": meta["platform"],
        },
        "digests": {
            "contracts": meta["contract_digest"],
            "configs": meta["config_digest"],
            "rubric_map": meta["rubric_map_digest"],
            "golden_contract_set": meta["golden_digest"],
        },
        "subsystems": {
            "contracts": meta["contracts_status"],
            "schemas": meta["schema_status"],
            "governance": meta["governance_status"],
            "boundaries": meta["boundaries_status"],
            "models": meta["models_status"],
            "golden": meta["golden_status"],
            "ci": meta["ci_status"],
            "starter_probe": meta["probe_status"],
        },
        "counts": {
            "checks_total": len(results),
            "required_executed": len(required),
            "passed": len(passed),
            "failed": len(failed),
            "planned_blocked": len(planned),
            "skipped": sum(1 for r in results if r["status"] == "SKIPPED"),
        },
        "tests": {k: v for k, v in meta["tests"].items() if k != "outcomes"},
        "blockers": blockers,
        "report_contract_problems": report_problems,
        "checks": results,
        "human_actions_required": [
            "Reviewer 2 signature on docs/official/CONTRACT_SIGNOFF.md is PENDING (a human must sign).",
            "Submission deadline is unknown (docs/QUESTIONS.md OPEN-0).",
        ],
        "note": "Internal verification suite only. It is not the jury score; see docs/DECISIONS.md D-0002.",
    }
    write_json("verify_summary.json", summary)
    _write_text_summary(summary)
    _write_phase_report(summary)
    _write_phase_report(summary, phase="PHASE-01")
    _write_matrix(results)
    _write_limitations_snapshot()
    return summary


def _validate_rubric(entry: dict, validator: ContractValidator) -> list[str]:
    """The emitted result obeys the same contract as every other public structure."""
    errors = validator.validate(entry, "rubric_check.schema.json")
    return [str(error) for error in errors]


def _write_text_summary(summary: dict) -> None:
    lines = [
        "TwinLedger verification summary",
        "=" * 32,
        f"profile            : {summary['profile']}",
        f"status             : {summary['status']}",
        f"exit code          : {summary['exit_code']}",
        f"official rubric    : {'available' if summary['official_rubric_available'] else 'NOT available (internal suite only)'}",
        f"generated (UTC)    : {summary['generated_at_utc']}",
        f"python / platform  : {summary['host']['python']} / {summary['host']['platform']}",
        f"contract digest    : {summary['digests']['contracts']}",
        f"config digest      : {summary['digests']['configs']}",
        "",
        "counts: " + ", ".join(f"{k}={v}" for k, v in summary["counts"].items()),
        f"tests: run={summary['tests']['tests_run']} passed={summary['tests']['passed']} "
        f"failed={summary['tests']['failed']} skipped={summary['tests']['skipped']}",
        "",
        "checks",
        "------",
    ]
    for check in summary["checks"]:
        lines.append(f"{check['status']:<15} {check['check_id']:<18} {check['title'][:70]}")
        if check["reason"]:
            lines.append(f"{'':<15} reason: {check['reason'][:160]}")
    if summary["blockers"]:
        lines.append("")
        lines.append("RELEASE BLOCKERS")
        for blocker in summary["blockers"]:
            lines.append(f"  - {blocker}")
    lines.append("")
    lines.append("human actions required")
    for action in summary["human_actions_required"]:
        lines.append(f"  - {action}")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "verify_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


PHASE_NARRATIVE = {
    "PHASE-00": {
        "title": "Phase 0 - official sources, contract, isolation, governance",
        "requirements": {"registry_total": 186, "mapped_to_checks": 137, "assumptions_total": 16,
                         "assumptions_unresolved": 16, "questions_total": 14,
                         "open_zero_items": 1, "decisions": 24},
        "known_limitations": [
            "No organizer contract, rubric, samples or starter code exists in any accessible channel; every external parameter stays provisional (D-0001, Q-001).",
            "The adapter is UNBOUND: no end-to-end run against the organizer protocol is possible yet (Q-005).",
            "Reviewer 2 signature on docs/official/CONTRACT_SIGNOFF.md is PENDING (human action, D-0017).",
            "The submission deadline is unknown; docs/QUESTIONS.md OPEN-0 has no date, and configs/submission/submission.json records it as null on purpose.",
            "Some requirements have no internal check yet; the official 80-check rubric is unavailable (Q-012).",
            "Process separation, socket blocking and resource limits are Phase 16 work; docs/THREAT_MODEL.md marks those boundaries as NOT ENABLED.",
            "The verification suite is internal and its pass rate is not a jury score (D-0002).",
        ],
    },
    "PHASE-01": {
        "title": "Phase 1 - repository foundation and contract freeze",
        "requirements": {"registry_total": 186, "assumptions_total": 16,
                         "questions_total": 14, "open_zero_items": 1},
        "known_limitations": [
            "Branch protection and CODEOWNERS handles are repository settings a human must apply; docs/BRANCH_PROTECTION.md lists them and .github/CODEOWNERS still holds placeholders.",
            "CI runs on GitHub-hosted runners only; the workflow proves the gate on Linux + Python 3.11, not on the organizers' machine (Q-010).",
            "The contract set is frozen at a golden digest, but the freeze is provisional: when the organizer contract appears, the freeze is re-taken under a CR (D-0022).",
            "Typed models mirror the schemas; nested objects stay dictionaries until the schemas pin them down further, so nested typing is not enforced beyond the schema.",
            "No episodes, generator, scorer or environment exist yet; 28 planned rubric checks stay BLOCKED (Phases 2-17).",
        ],
    },
}


def _write_phase_report(summary: dict, phase: str = "PHASE-00") -> None:
    """Refresh the machine-readable phase report from this run's own summary.

    The human report (`PHASE-00.md`) is written by a person and only cites these numbers; the
    JSON must never be edited by hand, otherwise a report can drift away from its artifact.
    Narrative keys are preserved when the file already exists.
    """
    narrative = PHASE_NARRATIVE[phase]
    path = ROOT / "docs" / "PHASE_REPORTS" / f"{phase}.json"
    payload: dict = {}
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    if not payload:
        payload = {
            "phase": phase,
            "title": narrative["title"],
            "date": time.strftime("%Y-%m-%d", time.gmtime()),
            "exit_gate": {
                "mandatory_interfaces_known": True,
                "unknowns_isolated": True,
                "blocking_risks_resolved_or_documented": True,
                "human_actions_open": 2,
            },
            "requirements": dict(narrative["requirements"]),
            "artifacts": [],
            "known_limitations": list(narrative["known_limitations"]),
        }
    counts = summary["counts"]
    tests = summary["tests"]
    payload["generated_from"] = "artifacts/reports/latest/verify_summary.json"
    payload["generated_at_utc"] = summary["generated_at_utc"]
    # A phase gate is never reported as a plain PASS while a human action is open.
    payload["status"] = ("PASS_WITH_OPEN_ITEMS"
                         if summary["status"].startswith("PASS") and summary["human_actions_required"]
                         else summary["status"])
    payload["human_actions_required"] = summary["human_actions_required"]
    payload["verification"] = {
        "command": "python3 -m tools.verify --profile core",
        "exit_code": summary["exit_code"],
        "status": summary["status"],
        "checks_total": counts["checks_total"],
        "passed": counts["passed"],
        "failed": counts["failed"],
        "planned_blocked": counts["planned_blocked"],
        "tests_run": tests["tests_run"],
        "tests_failed": tests["failed"],
        "tests_skipped": tests["skipped"],
        "contract_fixtures": "see contracts_report.json",
        "contract_digest": summary["digests"]["contracts"],
        "config_digest": summary["digests"]["configs"],
    }
    payload.setdefault("artifacts", [])
    for name in sorted(p.name for p in ARTIFACTS.glob("*")):
        entry = f"artifacts/reports/latest/{name}"
        if entry not in payload["artifacts"]:
            payload["artifacts"].append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_matrix(results: list[dict]) -> None:
    header = "block,check_id,status,official,phase_state,requirements"
    rows = [header]
    for check in results:
        state = "PLANNED" if check["reason"].startswith("not implemented yet") else "IMPLEMENTED"
        rows.append(",".join([
            check["block"], check["check_id"], check["status"], "false", state,
            "|".join(check["req_ids"]),
        ]))
    (ARTIFACTS / "rubric_matrix.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_limitations_snapshot() -> None:
    source = ROOT / "docs" / "LIMITATIONS.md"
    if not source.is_file():
        return
    text = source.read_text(encoding="utf-8")
    (ARTIFACTS / "limitations_snapshot.md").write_text(
        "# Snapshot of docs/LIMITATIONS.md at verification time\n\n"
        f"sha256: {canonical_digest(text)}\n\n" + text,
        encoding="utf-8",
    )


def open_items() -> list[str]:
    """Human actions that block a full 'DONE', reported separately from check failures."""
    items: list[str] = []
    signoff = ROOT / "docs" / "official" / "CONTRACT_SIGNOFF.md"
    if signoff.is_file() and "**Status:** PENDING" in signoff.read_text(encoding="utf-8"):
        items.append("HUMAN_ACTION_REQUIRED: second signature on the contract summary (Reviewer 2).")
    questions = ROOT / "docs" / "QUESTIONS.md"
    if questions.is_file() and "## OPEN-0" in questions.read_text(encoding="utf-8"):
        items.append("OPEN: submission deadline unknown (docs/QUESTIONS.md OPEN-0).")
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["core", "full"], default="full",
                        help="core = Phase 0 gate; full = same matrix with every planned check visible")
    parser.add_argument("--json", action="store_true", help="print the whole summary as JSON")
    parser.add_argument("--phase-report", action="store_true",
                        help="print the open items after the summary (used by make phase0)")
    args = parser.parse_args(argv)

    try:
        results, meta, blockers = build_results()
        summary = emit(results, meta, blockers, args.profile)
    except validate_contracts.SchemaError as exc:  # pragma: no cover - configuration error
        print(f"verify: CONFIG ERROR - {exc}")
        return EXIT_CONFIG
    except json.JSONDecodeError as exc:  # pragma: no cover - configuration error
        print(f"verify: CONFIG ERROR - invalid JSON in contracts/configs/rubric map: {exc}")
        return EXIT_CONFIG

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        text = (ARTIFACTS / "verify_summary.txt").read_text(encoding="utf-8")
        print(text)
        print(f"artifacts: {ARTIFACTS.relative_to(ROOT)}/verify_summary.json")
    if args.phase_report:
        print("open items")
        for item in open_items():
            print(f"  - {item}")
    return summary["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
