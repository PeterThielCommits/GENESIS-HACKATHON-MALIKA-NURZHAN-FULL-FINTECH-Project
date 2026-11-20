"""AST import-boundary and offline-dependency scan (REQ-ARC-001..003, REQ-OPS-001).

Every ``.py`` file is classified into a zone by its top-level directory, and the layer
table below (derived from master spec §6) decides which zones it may import. The scan is
static and offline, and it fails on the first violation instead of "reviewing" it.

Rules that exist today cover the modules that exist today; when ``env/``, ``scoring/`` or
``arena/`` appear in later phases they are already covered by the same table, so a
forbidden import fails the build without anyone editing this tool.

Usage:
    python -m tools.check_import_boundaries [--json]
Exit codes: 0 clean, 1 violation, 2 configuration error.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "artifacts", "build", "dist", "episodes"}

# zone -> zones it must not import
FORBIDDEN: dict[str, frozenset[str]] = {
    "adapter": frozenset({"gen", "verifier", "scoring", "seal", "env", "harness", "arena", "policy", "judge"}),
    "gen": frozenset({"verifier", "env", "scoring", "seal", "harness", "arena", "policy", "judge", "adapter"}),
    "verifier": frozenset({"gen", "env", "scoring", "seal", "harness", "arena", "policy", "adapter"}),
    "env": frozenset({"gen", "verifier", "scoring", "seal", "arena", "policy", "judge", "adapter"}),
    "scoring": frozenset({"gen", "env", "harness", "arena", "policy", "adapter", "judge"}),
    "seal": frozenset({"gen", "verifier", "env", "scoring", "harness", "arena", "policy", "judge", "adapter"}),
    "harness": frozenset({"gen", "verifier", "seal_internals", "policy", "judge"}),
    "arena": frozenset({"gen", "verifier", "scoring", "seal", "env", "judge"}),
    "invariants": frozenset({"gen", "verifier", "env", "scoring", "harness", "arena", "adapter"}),
    "metamorphic": frozenset({"scoring", "seal", "harness", "adapter"}),
    # `models/` is a typed mirror of contracts/: it may only depend on the contracts and on
    # the stdlib, and no other zone may be re-implemented inside it.
    "models": frozenset({"gen", "verifier", "env", "scoring", "seal", "harness", "arena",
                         "policy", "judge", "adapter"}),
    "judge": frozenset(),
    "tools": frozenset({"env", "scoring", "seal", "harness", "arena", "gen", "verifier"}),
    "tests": frozenset(),
    "contracts": frozenset(),
    "spec": frozenset(),
    "configs": frozenset(),
    "docs": frozenset(),
}

# Strings that must never appear in env/ (REQ-ARC-002) or policy code (REQ-ARC-003).
FORBIDDEN_TOKENS = {
    "env": ("truth.json", "provenance", "sealed/", "mutation_", "master_seed"),
    "policy": ("truth.json", "provenance", "scoring.", "seal.", "private"),
}


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        files.append(path)
    return files


def zone_of(path: Path) -> str:
    rel = path.relative_to(ROOT)
    if len(rel.parts) == 1:
        return "root"
    return rel.parts[0]


def imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import: resolved by package layout, not scanned
                continue
            if node.module:
                found.append((node.module.split(".")[0], node.lineno))
    return found


def scan() -> dict:
    violations: list[dict] = []
    third_party: list[dict] = []
    token_hits: list[dict] = []
    scanned = 0
    stdlib = set(sys.stdlib_module_names)

    for path in iter_python_files():
        zone = zone_of(path)
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel)
        except SyntaxError as exc:
            violations.append({"file": rel, "line": exc.lineno or 0, "rule": "PARSE", "detail": str(exc)})
            continue
        scanned += 1

        forbidden = FORBIDDEN.get(zone, frozenset())
        for module, line in imported_modules(tree):
            if module in forbidden:
                violations.append({
                    "file": rel, "line": line, "rule": "IMPORT_BOUNDARY",
                    "detail": f"zone '{zone}' must not import zone '{module}' (master spec §6)",
                })
            internal = module in FORBIDDEN or module in {"contracts", "models"}
            if module not in stdlib and not internal and module != "twinledger":
                third_party.append({"file": rel, "line": line, "module": module,
                                    "detail": "non-stdlib import in the mandatory path (REQ-OPS-001)"})

        # zone-scoped forbidden token scan (strings only, comments excluded by ast)
        scan_zone = "policy" if "/policies/" in rel else zone
        for token in FORBIDDEN_TOKENS.get(scan_zone, ()):
            if token in source:
                token_hits.append({"file": rel, "token": token, "zone": scan_zone,
                                   "detail": "sealed/target token referenced from a public zone (REQ-ARC-002/003)"})

    status = "PASS" if not violations and not third_party and not token_hits else "FAIL"
    return {
        "check": "import_boundaries",
        "status": status,
        "files_scanned": scanned,
        "layers": {zone: sorted(v) for zone, v in FORBIDDEN.items() if v},
        "violations": violations,
        "third_party_imports": third_party,
        "forbidden_token_hits": token_hits,
        "note": "Only zones that exist are scanned; the rule table already covers later phases.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = scan()
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"import boundaries: {result['status']} ({result['files_scanned']} files)")
        for item in result["violations"] + result["third_party_imports"] + result["forbidden_token_hits"]:
            print(f"  FAIL {item['file']}:{item.get('line', '?')} {item.get('rule', item.get('token'))} - {item['detail']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
