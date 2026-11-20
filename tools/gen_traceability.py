"""Generate docs/RUBRIC_TRACEABILITY.md from the rubric map and the requirement registry.

The document used to be written by hand next to the JSON it describes, which is exactly how a
traceability table becomes fiction. It is now generated, and ``--check`` fails the build when the
file on disk and the registries disagree.

Usage:
    python -m tools.gen_traceability --write   # regenerate
    python -m tools.gen_traceability --check   # verify the committed file is current
Exit codes: 0 current, 1 stale/differs, 2 configuration error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "RUBRIC_TRACEABILITY.md"

HEADER = """# RUBRIC TRACEABILITY

Organizer criterion → REQ id → internal check → command → artifact.

**This file is generated** by `python3 -m tools.gen_traceability --write` from
`judge/rubric_map.json` and `docs/REQUIREMENTS.json`; `make lint` and `GOV-RUBRIC-01` fail if it
is stale. Do not edit it by hand — edit the registries.
"""


def build() -> str:
    rubric = json.loads((ROOT / "judge" / "rubric_map.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "docs" / "REQUIREMENTS.json").read_text(encoding="utf-8"))
    requirements = {item["id"]: item for item in registry["requirements"]}
    checks = rubric["internal_checks"]

    mapped = {req_id for check in checks for req_id in check["req_ids"]}
    unmapped = sorted(set(requirements) - mapped)

    lines: list[str] = [HEADER]
    lines.append("## Status of the official rubric\n")
    lines.append(
        "**There is no official rubric in this repository.** `configs/rubric/provisional.json` "
        "records `official_rubric_available: false` and `judge/rubric_map.json` marks every entry "
        "`official: false`. The block weights below are our *preliminary* reading of the master "
        "specification §0.3 and must be replaced — never silently reinterpreted — when the "
        "organizers publish the real rubric (Q-012).\n")
    lines.append("| Block | Provisional points | Assumed official checks | Internal checks (implemented / planned) |")
    lines.append("|-------|-------------------|------------------------|------------------------------------------|")
    for block in rubric["blocks"]:
        own = [c for c in checks if c["block"] == block["block"]]
        implemented = sum(1 for c in own if c["declared_state"] == "IMPLEMENTED")
        lines.append(f"| `{block['block']}` — {block['title']} | {block['provisional_points']} | "
                     f"{block['assumed_official_checks']} | {len(own)} ({implemented} / {len(own) - implemented}) |")
    total_points = sum(b["provisional_points"] for b in rubric["blocks"])
    total_official = sum(b["assumed_official_checks"] for b in rubric["blocks"])
    total_impl = sum(1 for c in checks if c["declared_state"] == "IMPLEMENTED")
    lines.append(f"| **Total** | **{total_points}** | **{total_official}** | **{len(checks)}** "
                 f"({total_impl} implemented) |")
    lines.append("")

    lines.append("## Requirement coverage\n")
    lines.append(f"`{len(mapped)} / {len(requirements)}` requirements from "
                 f"`docs/REQUIREMENTS.json` are mapped to at least one internal check today. "
                 f"`{len(unmapped)}` are not, and every one of them belongs to a phase that does "
                 f"not exist yet. They are **not** silently dropped: the list below is generated "
                 f"from the registry, so the gap stays visible and countable.\n")
    areas: dict[str, list[str]] = {}
    for req_id in unmapped:
        area = req_id.split("-")[1]
        areas.setdefault(area, []).append(req_id)
    if areas:
        lines.append("| Area | Unmapped requirements |")
        lines.append("|------|-----------------------|")
        for area in sorted(areas):
            joined = ", ".join(areas[area])
            lines.append(f"| `{area}` | {len(areas[area])}: {joined} |")
    else:
        lines.append("Every requirement is mapped to at least one internal check.")
    lines.append("")

    lines.append("## Check matrix\n")
    lines.append("| Check | Block | Phase | State | Requirements | Command | Artifact |")
    lines.append("|-------|-------|-------|-------|--------------|---------|----------|")
    for check in checks:
        lines.append(f"| `{check['check_id']}` | `{check['block']}` | {check['phase']} | "
                     f"{check['declared_state']} | {', '.join(check['req_ids'])} | "
                     f"`{check['command']}` | `{check['artifact']}` |")
    lines.append("")

    lines.append("## Rules\n")
    for name, text in rubric["rules"].items():
        lines.append(f"* **{name}** — {text}")
    lines.append("")
    lines.append("## How a check appears in `make verify`\n")
    lines.append("* `IMPLEMENTED` checks are executed; their status is `PASS`, `FAIL` or `SKIPPED` "
                 "with a real command and an artifact reference.")
    lines.append("* `PLANNED` checks are emitted as `BLOCKED` with the phase that will implement "
                 "them. They are never counted as passing and never omitted from the report.")
    lines.append("* A check whose dependency is absent is `SKIPPED` with a reason (REQ-JUDGE-003).")
    lines.append("* Exit code `0` requires every executed check to pass; `4` is reserved for a "
                 "release blocker (leak or a false official claim).")
    lines.append("")
    lines.append("## When the official rubric arrives\n")
    lines.append("1. Archive it under `docs/official/` with `classification: OFFICIAL_ORGANIZER` and its SHA-256.")
    lines.append("2. Open a `docs/CR/` entry describing the diff against these provisional blocks.")
    lines.append("3. Add a mirrored internal test per official check and set `official: true` with "
                 "the quoted source and identifier.")
    lines.append("4. Set `official_rubric_available: true` — only then may a report carry an official figure.")
    lines.append("5. Re-run `make verify` and regenerate this file; the phase report records the new numbers.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        content = build()
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        print(f"traceability: CONFIG ERROR - {exc}")
        return 2
    if args.write:
        DOC.write_text(content, encoding="utf-8")
        print(f"traceability: wrote {DOC.relative_to(ROOT)}")
        return 0
    current = DOC.read_text(encoding="utf-8") if DOC.is_file() else ""
    if current != content:
        print("traceability: STALE - docs/RUBRIC_TRACEABILITY.md differs from the registries")
        print("traceability: run `python3 -m tools.gen_traceability --write`")
        current_lines, new_lines = current.splitlines(), content.splitlines()
        for index in range(min(len(current_lines), len(new_lines))):
            if current_lines[index] != new_lines[index]:
                print(f"  first difference at line {index + 1}:")
                print(f"    file: {current_lines[index][:160]}")
                print(f"    want: {new_lines[index][:160]}")
                break
        return 1
    print("traceability: current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
