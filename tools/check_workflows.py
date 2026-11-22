#!/usr/bin/env python3
"""Static guard for the GitHub Actions workflow files.

Why this exists
---------------
A GitHub Actions workflow that does not parse is worse than no workflow at
all: the run is created, fails immediately with **zero jobs**, and the only
hint in the UI is "This run likely failed because of a workflow file issue".
Nothing in the repository fails, because nothing in the repository runs.

The trap that hit Phase 17 was a plain (unquoted) YAML scalar containing a
colon followed by a space::

    - name: Evidence freeze (Phase 17: the committed archive must match the tree)

YAML reads ``Phase 17: the committed...`` as a mapping, not as text, so the
whole file stops being valid YAML and *every* job of the workflow disappears.
The same applies to a tab used for indentation.

What this tool checks
---------------------
1. **Full parse** when PyYAML is importable (the runner image usually has
   it): the file must load and must define at least one job.
2. **Heuristic scan** always: no plain scalar may contain ``": "`` and no
   line may be indented with a tab. Both are YAML parse breakers that a
   regex can catch reliably, and the tool must work with the standard
   library alone (the hardened offline container has no third-party
   packages).

Exit codes (TZ 23.3 style):
  0  every workflow file is well formed
  4  at least one workflow file is malformed
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

#: A mapping key inside a plain scalar. YAML only allows a colon inside a
#: plain scalar when it is NOT followed by a space.
_COLON_SPACE = re.compile(r":\s")

#: ``- name: <value>`` / ``name: <value>`` style keys whose value is a plain
#: (unquoted) scalar. Quoted values are exempt: inside quotes a colon is
#: ordinary text.
_KEY_VALUE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_.\-]+):\s+(?P<value>.+?)\s*$")
_LIST_ITEM = re.compile(r"^(?P<indent>\s*)-\s+(?P<key>[A-Za-z0-9_.\-]+):\s+(?P<value>.+?)\s*$")


def _is_quoted(value: str) -> bool:
    return len(value) >= 2 and value[0] == value[-1] and value[0] in "'\""


def scan_text(path: Path, text: str) -> list[str]:
    """Return the YAML hazards found in ``text`` (stdlib-only heuristics)."""
    problems: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith("\t") or line.lstrip(" ").startswith("\t"):
            problems.append(f"{path.name}:{number}: tab used for indentation (YAML forbids it)")
            continue
        match = _LIST_ITEM.match(line) or _KEY_VALUE.match(line)
        if not match:
            continue
        value = match.group("value")
        if _is_quoted(value):
            continue
        # A block scalar header (``|`` / ``>``) carries no inline value.
        if value in {"|", ">", "|-", ">-", "|+", ">+"}:
            continue
        if _COLON_SPACE.search(value):
            problems.append(
                f"{path.name}:{number}: unquoted value contains ': ' "
                f"({value.strip()[:70]!r}) - quote it or drop the colon, "
                "otherwise the workflow file stops being valid YAML"
            )
    return problems


def parse_with_pyyaml(path: Path, text: str) -> list[str]:
    """Full YAML parse, when PyYAML happens to be available."""
    try:
        import yaml  # type: ignore[import-not-found]
    except Exception:
        return []
    try:
        doc = yaml.safe_load(text)
    except Exception as exc:
        return [f"{path.name}: YAML parse error: {exc}"]
    if not isinstance(doc, dict):
        return [f"{path.name}: the workflow must be a mapping"]
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        return [f"{path.name}: the workflow defines no jobs"]
    return []


#: A top-level ``jobs:`` mapping. A workflow without one runs nothing.
_JOBS_KEY = re.compile(r"^jobs:\s*(?:#.*)?$", re.MULTILINE)


def check_workflows(workflow_dir: Path = WORKFLOW_DIR, optional: bool = False) -> list[str]:
    """Check every workflow file; return the list of problems (empty = OK).

    ``optional=True`` treats a missing workflow directory as "nothing to
    check" instead of a problem. That mode is used inside the hardened
    offline container, where the CI configuration is not part of the
    submission image; the *repository* is always checked strictly (see
    ``tests/judge/test_workflows.py``).
    """
    problems: list[str] = []
    if not workflow_dir.is_dir():
        if optional:
            return []
        return [f"missing workflow directory: {workflow_dir}"]
    files = sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml"))
    if not files:
        return [f"no workflow files in {workflow_dir}"]
    for path in files:
        text = path.read_text(encoding="utf-8")
        problems.extend(parse_with_pyyaml(path, text))
        problems.extend(scan_text(path, text))
        if not _JOBS_KEY.search(text):
            problems.append(f"{path.name}: no top-level 'jobs:' mapping - the workflow would run nothing")
    return problems


def cw_dir_is_dir() -> bool:
    """Whether the workflow directory exists in this tree."""
    return WORKFLOW_DIR.is_dir()


#: YAML files outside the workflow directory that the tooling also parses
#: (``docker-compose.yml`` for the container, ``spec/*.yaml`` for the
#: contracts). A colon-space in one of them breaks the tool that reads it.
AUXILIARY_YAML: tuple[str, ...] = (
    "docker-compose.yml",
    "spec/anomaly_catalog.yaml",
    "spec/invariants.yaml",
)


def check_auxiliary_yaml(repo_root: Path = REPO_ROOT) -> list[str]:
    """Scan the other YAML files of the repository for the same hazards."""
    problems: list[str] = []
    for rel in AUXILIARY_YAML:
        path = repo_root / rel
        if not path.is_file():
            continue
        problems.extend(scan_text(path, path.read_text(encoding="utf-8")))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static guard for the GitHub Actions workflows")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable summary")
    parser.add_argument(
        "--optional",
        action="store_true",
        help="Treat a missing workflow directory as 'nothing to check' (offline container)",
    )
    args = parser.parse_args(argv)

    problems = check_workflows(optional=args.optional)
    problems.extend(check_auxiliary_yaml())
    if args.json:
        import json

        print(json.dumps({"status": "PASS" if not problems else "FAIL", "problems": problems}, indent=2))
        return 0 if not problems else 4
    if problems:
        print("workflow check: FAIL")
        for problem in problems:
            print(f"  - {problem}")
        return 4
    if args.optional and not cw_dir_is_dir():
        print("workflow check: SKIP (no workflow directory in this tree)")
        return 0
    print("workflow check: PASS (every workflow file is well formed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
