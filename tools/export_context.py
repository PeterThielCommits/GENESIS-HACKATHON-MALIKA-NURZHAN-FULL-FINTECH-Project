#!/usr/bin/env python3
"""Export a machine-readable snapshot of the project context.

Why this exists
---------------
Prose documentation drifts. This tool derives the *facts* that agents need — the
invariant catalogue, the anomaly error matrix, the operator registry, the frozen
schema inventory, the file map and the canonical commands — directly from the code
and writes them to ``docs/CONTEXT/PROJECT_CONTEXT.json``.

``tests/docs/test_docs_consistency.py`` regenerates this file and fails if the
committed copy is stale, so the single source of truth cannot silently diverge.

Usage:
    python3 tools/export_context.py            # write the file
    python3 tools/export_context.py --check    # exit 1 if the committed file is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.book_model import JSON_TABLES, PUBLIC_FILE_ORDER  # noqa: E402
from contracts.models import TABLES  # noqa: E402
from gen.config import load_generator_config  # noqa: E402
from gen.errors import registry  # noqa: E402
from gen.errors.signatures import ERROR_MATRIX, SUBTYPE_MATRIX  # noqa: E402

TARGET = REPO_ROOT / "docs" / "CONTEXT" / "PROJECT_CONTEXT.json"

INVARIANT_CATALOGUE: dict[str, str] = {
    "INV-01": "JE_BALANCE — debit equals credit in every entry",
    "INV-02": "TRIAL_BALANCE — functional postings net to zero across the book",
    "INV-03": "AP_SUBLEDGER_VS_DOCS — receivable ledger equals document open balances",
    "INV-04": "OPEN_BALANCE — open balance reconciled with payments and credit notes",
    "INV-05": "AGING — aging buckets follow due date and remaining balance",
    "INV-06": "BANK_MATCH — bank lines match payments or carry a justified status",
    "INV-07": "FX_POLICY — booked rate equals the policy-required rate",
    "INV-08": "FX_RECALC — functional amount recomputes from the booked rate",
    "INV-09": "CUTOFF — posting period follows the recognition policy",
    "INV-10": "PERIOD_TOTALS — period totals use the entry's own timestamp date",
    "INV-11": "ID_UNIQUENESS — ids unique per table and across document tables",
    "INV-12": "REFERENTIAL — every explicit reference resolves",
    "INV-13": "CURRENCY_EXPONENT — scale and minor units are correct",
    "INV-14": "TIMEZONE_VALID — timestamps are unambiguous ISO-8601 with offset",
    "INV-15": "ALLOCATION_CONSERVATION — allocations do not exceed the payment",
    "INV-16": "CREDIT_NOTE_LIMIT — credit notes respect the policy cap",
    "INV-17": "DOCUMENT_STATUS — stored status equals derived status",
}

LAYERS: dict[str, dict[str, object]] = {
    "contracts": {
        "role": "frozen schemas, row models, immutable Book, canonical JSON, error types",
        "may_import": ["core"],
        "must_not_import": ["gen", "invariants", "verifier"],
    },
    "core": {
        "role": "money (integer minor units), time rules (zoneinfo/DST), deterministic ids",
        "may_import": ["contracts"],
        "must_not_import": ["gen", "invariants", "verifier"],
    },
    "invariants": {
        "role": "INV-01..17 checks over the public book model",
        "may_import": ["contracts", "core"],
        "must_not_import": ["gen"],
    },
    "gen": {
        "role": "clean twin builder, mutation operators, diff, truth, reject, publish",
        "may_import": ["contracts", "core", "invariants"],
        "must_not_import": [],
    },
    "verifier": {
        "role": "independent verifier (Phase 8) — public data only",
        "may_import": ["contracts", "core"],
        "must_not_import": ["gen", "invariants"],
    },
}

COMMANDS: list[dict[str, str]] = [
    {"command": "make test", "purpose": "full stdlib test suite (no skips expected)"},
    {"command": "make sweep", "purpose": "24 seeds x L1/L2 gate sweep with JSON output"},
    {"command": "make verify", "purpose": "tests + sweep = the phase exit gate"},
    {"command": "python3 tools/export_context.py --check", "purpose": "detect stale context snapshot"},
    {
        "command": "python3 tools/phase4_sweep.py --seeds 8 --json /tmp/s.json",
        "purpose": "small ad-hoc gate sweep",
    },
]


def build_context() -> dict[str, object]:
    config = load_generator_config()
    version = json.loads((REPO_ROOT / "contracts" / "version.json").read_text(encoding="utf-8"))
    schema_files = sorted(path.name for path in (REPO_ROOT / "contracts").glob("*.schema.json"))
    return {
        "context_version": "1.0.0",
        "generated_by": "tools/export_context.py",
        "generated_for": "TwinLedger v3.0 generator (Phase 4 complete)",
        "project": {
            "name": "TwinLedger v3.0",
            "kind": "synthetic twin accounting benchmark, generator side",
            "python": ">=3.11",
            "runtime_dependencies": [],
            "offline": True,
            "contract_version": version["contract_version"],
            "contract_status": version["status"],
            "generator_version": config.raw["generator_version"],
            "config_version": config.raw["config_version"],
        },
        "layers": LAYERS,
        "book": {
            "tables": list(TABLES),
            "json_tables": list(JSON_TABLES),
            "public_files": list(PUBLIC_FILE_ORDER),
            "public_file_count": len(PUBLIC_FILE_ORDER),
            "sealed_files": [
                "truth.json",
                "provenance.json",
                "verifier_crosscheck.json",
                "reject_log.json",
            ],
        },
        "schemas": {
            "count": len(schema_files),
            "files": schema_files,
            "declared_in_version_json": sorted(version["schemas"]),
        },
        "invariants": {
            "count": len(INVARIANT_CATALOGUE),
            "catalogue": INVARIANT_CATALOGUE,
        },
        "operators": [entry.describe() for entry in registry.all_entries()],
        "anomaly_types": {
            "implemented": list(registry.anomaly_types()),
            "required_by_phase_4": list(registry.REQUIRED_ANOMALY_TYPES),
            "error_matrix": {key: {k: list(v) for k, v in value.items()} for key, value in ERROR_MATRIX.items()},
            "subtype_matrix": {
                f"{key[0]}/{key[1]}": {k: list(v) for k, v in value.items()}
                for key, value in SUBTYPE_MATRIX.items()
            },
        },
        "difficulty_profiles": config.raw["difficulty_profiles"],
        "reject_reasons": list(_reject_reasons()),
        "commands": COMMANDS,
        "documentation": {
            "entry_point": "docs/README.md",
            "handover": "docs/CONTEXT/NEXT_AGENT.md",
            "status": "docs/STATUS.md",
            "architecture": "docs/CONTEXT/ARCHITECTURE.md",
            "invariants": "docs/CONTEXT/INVARIANTS.md",
            "error_matrix": "docs/CONTEXT/ERROR_MATRIX.md",
            "testing": "docs/CONTEXT/TESTING.md",
            "data_contracts": "docs/CONTEXT/DATA_CONTRACTS.md",
            "determinism": "docs/CONTEXT/DETERMINISM.md",
            "glossary": "docs/GLOSSARY.md",
            "protocol": "docs/CONTEXT/AI_HANDOFF_PROTOCOL.md",
            "decisions": "docs/DECISIONS.md",
            "phase_reports": "docs/PHASE_REPORTS/",
            "agent_reports": "docs/AGENT_REPORTS/",
        },
    }


def _reject_reasons() -> tuple[str, ...]:
    from gen.reject import REJECT_REASONS

    return REJECT_REASONS


def render() -> str:
    return json.dumps(build_context(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the project context snapshot")
    parser.add_argument("--check", action="store_true", help="fail if the committed file is stale")
    parser.add_argument("--out", default=str(TARGET))
    args = parser.parse_args(argv)

    rendered = render()
    target = Path(args.out)
    if args.check:
        if not target.exists():
            print(f"MISSING: {target}")
            return 1
        if target.read_text(encoding="utf-8") != rendered:
            print(f"STALE: {target} — run python3 tools/export_context.py")
            return 1
        print(f"OK: {target} is current")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
