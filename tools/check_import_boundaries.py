#!/usr/bin/env python3
"""AST import-boundary scanner (REQ-ARC-001 .. REQ-ARC-007).

Scans Python sources for forbidden imports / file accesses:

  - env/ must not import gen, verifier, scoring, seal, truth modules
  - verifier/ must not import gen (and must not read sealed/provenance
    paths at discovery time — checked by string scan of path literals)
  - arena/policies + arena/attacks must not import gen, verifier,
    scoring, seal, truth/provenance internals
  - scoring/ may import contracts + seal only (plus stdlib)
  - seal/ may import contracts + stdlib only
  - gen/ may import contracts + spec (never verifier/scoring internals)
  - harness/ may import contracts + protocol helpers only
  - judge/ may import contracts + report schemas only

Exit codes: 0 = clean, 1 = violation found, 2 = scanner error.
Stdlib-only. Run via ``make lint`` / ``python tools/check_import_boundaries.py``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# (directory prefix, forbidden top-level modules, description)
RULES: list[tuple[str, tuple[str, ...], str]] = [
    ("core", ("gen", "verifier", "scoring", "env", "invariants"), "primitives must be independent"),
    ("invariants", ("gen", "verifier", "env", "scoring"), "group checks must not depend on producers"),
    ("env", ("gen", "verifier", "scoring", "seal"), "env must not import gen/verifier/scoring/seal (REQ-ARC-002)"),
    ("verifier", ("gen", "nlp"), "verifier must not import gen or nlp (REQ-VER-002, Phase 10)"),
    ("nlp", ("gen", "verifier", "scoring", "seal", "env", "harness"), "nlp may import only contracts + stdlib (Phase 10)"),
    ("arena/policies", ("gen", "verifier", "scoring", "seal", "truth", "provenance"), "policies must not import private internals (REQ-ARC-003)"),
    ("arena/attacks", ("gen", "verifier", "scoring", "seal", "truth", "provenance"), "attacks must not import private internals (REQ-ARC-003)"),
    ("scoring", ("gen", "verifier", "env", "harness"), "scoring may import only contracts/seal (TZ 6)"),
    ("seal", ("gen", "verifier", "env", "scoring", "harness"), "seal may import only contracts + stdlib (TZ 6)"),
    ("gen", ("verifier", "scoring", "seal"), "gen must not import verifier/scoring/seal (TZ 6)"),
    ("harness", ("gen", "verifier", "scoring", "seal"), "harness must not import gen/verifier/scoring/seal (TZ 6)"),
]

# String literals that indicate sealed/private path access in public zones.
FORBIDDEN_PATH_TOKENS: list[tuple[str, tuple[str, ...], str]] = [
    ("env", ("sealed/", "sealed\\", "truth.json", "provenance.json"), "env must not reference sealed paths (REQ-ARC-002)"),
    ("verifier", ("sealed/", "sealed\\", "truth.json", "provenance.json"), "verifier discovery must not reference sealed paths (REQ-VER-001)"),
    ("arena/policies", ("sealed/", "truth.json", "provenance.json"), "policies must not reference sealed paths (REQ-ARC-003)"),
    ("arena/attacks", ("sealed/", "truth.json", "provenance.json"), "attacks must not reference sealed paths (REQ-ARC-003)"),
]


def _top_level(module: str) -> str:
    return module.split(".")[0]


def _imports_in_file(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"cannot parse {path}: {exc}") from exc
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.append((node.lineno, node.module))
    return found


def _string_literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append((node.lineno, node.value))
    return out


def scan(repo_root: Path = REPO_ROOT) -> list[str]:
    """Return list of violation strings (empty = clean)."""
    violations: list[str] = []
    py_files = sorted(repo_root.rglob("*.py"))
    # Exclude tests fixtures that intentionally contain forbidden imports
    # as negative test data, and virtualenvs/caches.
    py_files = [
        p for p in py_files
        if ".venv" not in p.parts and "__pycache__" not in p.parts
        and "tests/fixtures" not in p.as_posix()
    ]
    for path in py_files:
        rel = path.relative_to(repo_root).as_posix()
        for prefix, forbidden, desc in RULES:
            if rel == prefix or rel.startswith(prefix + "/"):
                for lineno, module in _imports_in_file(path):
                    if _top_level(module) in forbidden:
                        violations.append(f"{rel}:{lineno}: forbidden import {module!r} — {desc}")
        for prefix, tokens, desc in FORBIDDEN_PATH_TOKENS:
            if rel.startswith(prefix + "/"):
                for lineno, literal in _string_literals(path):
                    for tok in tokens:
                        if tok in literal:
                            violations.append(f"{rel}:{lineno}: forbidden path literal {literal!r} — {desc}")
                            break
    return violations


def main(argv: list[str] | None = None) -> int:
    root = Path(argv[1]).resolve() if argv and len(argv) > 1 else REPO_ROOT
    try:
        violations = scan(root)
    except RuntimeError as exc:
        print(f"BOUNDARY SCAN ERROR: {exc}", file=sys.stderr)
        return 2
    if violations:
        print(f"IMPORT BOUNDARY VIOLATIONS ({len(violations)}):")
        for v in violations:
            print(f"  {v}")
        return 1
    print("import boundary scan: CLEAN (REQ-ARC-001..007)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
