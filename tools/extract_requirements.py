"""Extract the normative requirement registry from the archived master specification.

Phase 0 task 0.3/0.4 requires an exact, machine-checkable list of every REQ-* identifier
so that later phases cannot silently drop a requirement. The registry is generated (not
hand-written) so it cannot drift from the archived text.

Usage:
    python -m tools.extract_requirements            # rewrite docs/REQUIREMENTS.json
    python -m tools.extract_requirements --check    # verify the committed file is current
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "official" / "master_tz" / "TwinLedger_v3_Master_TZ_AI_Agents.txt"
OUT = ROOT / "docs" / "REQUIREMENTS.json"

REQ_DEF = re.compile(r"^REQ-([A-Z]+)-([0-9]{3})\s+(.*)$")
REQ_ANY = re.compile(r"REQ-[A-Z]+-[0-9]{3}")

AREA_TITLES = {
    "PROD": "Product-level obligations (determinism, derivability, tooling)",
    "ORG": "Organisation, ownership and independence rules",
    "GH": "GitHub-first traceability and context preservation",
    "ARC": "Architecture and import boundaries",
    "CONTRACT": "Contracts, schemas and compatibility",
    "DATA": "Synthetic data model, IDs and sealed storage",
    "MONEY": "Money, currency exponent and rounding",
    "TIME": "Timezones, periods and cut-off",
    "GEN": "Deterministic generator and RNG streams",
    "ERR": "Anomaly operators and mutation correctness",
    "INV": "Invariant catalog and signatures",
    "VER": "Independent verifier and evidence graphs",
    "ENV": "Environment contract, tools, budget and errors",
    "SCORE": "Matcher, F1 and reward",
    "SEAL": "Process isolation, commit-reveal and replay",
    "NLP": "Multilingual text layer and prompt-injection robustness",
    "ARENA": "Arena policies, attacks and learnability",
    "LEAK": "Shortcut audit and canary fuzzing",
    "TEST": "Unit, property, metamorphic and mutation testing",
    "UNIQUE": "Differentiating research features",
    "OPS": "Runtime, dependencies and offline operation",
    "JUDGE": "Judge kit, make targets and reporting",
    "ADAPTER": "Organizer adapter",
}


def extract() -> dict:
    text = SPEC.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    lines = text.split("\n")

    definitions: dict[str, dict] = {}
    for number, line in enumerate(lines, start=1):
        match = REQ_DEF.match(line.rstrip())
        if not match:
            continue
        area, seq, body = match.groups()
        # Requirements are wrapped across indented continuation lines in the source.
        continuation: list[str] = []
        for follow in lines[number:]:
            if follow.startswith("  ") and follow.strip():
                continuation.append(follow.strip())
                continue
            break
        if continuation:
            body = " ".join([body.strip()] + continuation)
        req_id = f"REQ-{area}-{seq}"
        # First definition wins; duplicates in the source are reported instead of merged.
        if req_id in definitions:
            definitions[req_id].setdefault("duplicate_spec_lines", []).append(number)
            continue
        definitions[req_id] = {
            "id": req_id,
            "area": area,
            "area_title": AREA_TITLES.get(area, "Unclassified area"),
            "sequence": int(seq),
            "text": body.strip(),
            "spec_line": number,
            "origin": "MASTER_TZ",
            "official_status": "PROVISIONAL_MASTER_TZ",
            "official_status_note": (
                "Defined by the internal master specification. It becomes official only when the "
                "organizer document states the same obligation (see docs/DECISIONS.md D-0001)."
            ),
        }

    mentions_only = sorted({m for m in REQ_ANY.findall(text) if m not in definitions})
    areas: dict[str, dict] = {}
    for item in definitions.values():
        entry = areas.setdefault(item["area"], {"area": item["area"],
                                                "title": AREA_TITLES.get(item["area"], "Unclassified area"),
                                                "count": 0})
        entry["count"] += 1

    return {
        "registry_version": "1.0.0",
        "generated_by": "tools/extract_requirements.py",
        "generated_from": str(SPEC.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": digest,
        "source_lines": len(lines),
        "total_requirements": len(definitions),
        "areas": [areas[key] for key in sorted(areas)],
        "requirements": [definitions[key] for key in sorted(definitions, key=lambda r: (definitions[r]["area"], definitions[r]["sequence"]))],
        "mentions_without_definition": mentions_only,
        "notes": [
            "Definitions are lines that begin with REQ-<AREA>-<NNN> in the archived master specification.",
            "Identifiers appearing only inside examples or branch-name examples are listed in mentions_without_definition and are not requirements.",
            "This registry is regenerated by command; tests fail if the committed copy drifts from the archive.",
        ],
    }


def render(registry: dict) -> str:
    return json.dumps(registry, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed registry is stale")
    args = parser.parse_args(argv)

    if not SPEC.is_file():
        print(f"FAIL archived master specification not found at {SPEC.relative_to(ROOT)}")
        return 2

    rendered = render(extract())
    if args.check:
        if not OUT.is_file():
            print("FAIL docs/REQUIREMENTS.json is missing; run python -m tools.extract_requirements")
            return 1
        if OUT.read_text(encoding="utf-8") != rendered:
            print("FAIL docs/REQUIREMENTS.json is stale; run python -m tools.extract_requirements")
            return 1
        print(f"requirements registry: OK ({json.loads(rendered)['total_requirements']} requirements)")
        return 0

    OUT.write_text(rendered, encoding="utf-8")
    registry = json.loads(rendered)
    print(f"wrote {OUT.relative_to(ROOT)}: {registry['total_requirements']} requirements, "
          f"{len(registry['mentions_without_definition'])} mention-only identifiers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
