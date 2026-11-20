"""Validate twinledger contracts against their declared fixtures.

Usage:
    python -m tools.validate_contracts                 # human readable + exit code
    python -m tools.validate_contracts --json          # machine readable (judge/CI)
    python -m tools.validate_contracts --hash          # print the contract set digest

Exit codes follow the project-wide convention (master spec §23.3):
    0 all fixtures behaved as declared
    2 configuration/contract error (bad index, missing schema, unsupported keyword)
    1 at least one fixture disagreed with its declaration
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # direct execution support: python tools/validate_contracts.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.canonical_json import canonical_digest
from tools.jsonschema_lite import ContractValidator, SchemaError

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
FIXTURES = CONTRACTS / "fixtures"


class ContractCheckResult:
    def __init__(self) -> None:
        self.cases: list[dict] = []
        self.errors: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> dict:
        return {
            "check": "contracts",
            "status": "PASS" if self.ok else "FAIL",
            "cases_total": len(self.cases),
            "cases_passed": sum(1 for c in self.cases if c["status"] == "PASS"),
            "errors": self.errors,
            "cases": self.cases,
        }


def run() -> ContractCheckResult:
    result = ContractCheckResult()
    index_path = FIXTURES / "index.json"
    if not index_path.is_file():
        result.errors.append("contracts/fixtures/index.json is missing")
        return result

    index = json.loads(index_path.read_text(encoding="utf-8"))
    version = json.loads((CONTRACTS / "version.json").read_text(encoding="utf-8"))
    declared_schemas = {entry["file"] for entry in version["schemas"]}
    fixture_required = {entry["file"] for entry in version["schemas"] if entry.get("kind") != "definitions"}
    validator = ContractValidator(CONTRACTS)

    coverage: dict[str, set[str]] = {name: set() for name in fixture_required}
    for case in index.get("cases", []):
        schema_name = case.get("schema", "")
        entry = {
            "case_id": case.get("case_id", "?"),
            "schema": schema_name,
            "expect": case.get("expect", "?"),
            "status": "PASS",
            "failures": [],
        }
        if schema_name not in declared_schemas:
            entry["status"] = "FAIL"
            entry["failures"].append(f"schema {schema_name!r} is not declared in contracts/version.json")
        else:
            if schema_name in coverage:
                coverage[schema_name].add(entry["expect"])
            data_file = FIXTURES / case["file"]
            if not data_file.is_file():
                entry["status"] = "FAIL"
                entry["failures"].append(f"missing fixture file {case['file']}")
            else:
                try:
                    errors = validator.validate_file(data_file, schema_name)
                except SchemaError as exc:
                    entry["status"] = "FAIL"
                    entry["failures"].append(f"schema error: {exc}")
                else:
                    verdict = "valid" if not errors else "invalid"
                    if verdict != entry["expect"]:
                        entry["status"] = "FAIL"
                        rendered = "; ".join(str(e) for e in errors) or "no errors"
                        entry["failures"].append(f"expected {entry['expect']}, got {verdict} ({rendered})")
                    else:
                        for expected in case.get("expect_errors", []):
                            if not any(
                                e.path == expected["path"] and e.keyword == expected["keyword"]
                                for e in errors
                            ):
                                entry["status"] = "FAIL"
                                entry["failures"].append(
                                    f"missing expected error {expected['path']} [{expected['keyword']}]"
                                )
        result.cases.append(entry)
        if entry["failures"]:
            result.errors.extend(f"{entry['case_id']}: {msg}" for msg in entry["failures"])

    for schema_name, kinds in sorted(coverage.items()):
        missing = {"valid", "invalid"} - kinds
        if missing:
            result.errors.append(f"{schema_name}: no {'/'.join(sorted(missing))} fixture")
    return result


def contract_digest() -> str:
    """Digest of the frozen contract set (schema files only, canonical text)."""
    payload = {}
    for path in sorted(CONTRACTS.glob("*.json")):
        if path.name == "GOLDEN.json":
            continue  # freeze metadata, not part of the contract payload
        payload[path.name] = json.loads(path.read_text(encoding="utf-8"))
    return canonical_digest(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine readable JSON")
    parser.add_argument("--hash", action="store_true", help="print the contract set digest only")
    args = parser.parse_args(argv)

    try:
        result = run()
    except SchemaError as exc:
        print(json.dumps({"check": "contracts", "status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 2

    if args.hash:
        print(contract_digest())
        return 0

    summary = result.summary()
    summary["contract_digest"] = contract_digest()
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"contracts: {summary['status']} ({summary['cases_passed']}/{summary['cases_total']} fixtures)")
        print(f"contract_digest: {summary['contract_digest']}")
        for error in summary["errors"]:
            print(f"  FAIL {error}")
    if not result.ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
