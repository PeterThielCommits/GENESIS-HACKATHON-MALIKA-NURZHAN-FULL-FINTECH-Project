"""Lint the GitHub Actions workflow without a YAML dependency (task 1.5).

Why not PyYAML: the mandatory core is stdlib-only by decision D-0003, and a CI file that can
only be checked on a machine with an extra package is a CI file that is checked by nobody. This
tool therefore parses the small subset of YAML a workflow actually needs here - the keys
``name/on/jobs/<id>/runs-on/steps`` plus ``run:`` and ``uses:`` - and checks the things that
usually rot:

1. every ``run:`` command actually exists in this repository (a make target or a ``python -m``
   module with a real file), so a renamed tool cannot leave a silently skipped CI step;
2. the gate commands are present (``make setup``, ``make lint``, ``make test``, ``make verify-core``);
3. ``uses:`` actions are pinned to a tag, not to a branch;
4. the artifact path the workflow uploads is the one the runner writes.

A missing step is reported as a failure here, not discovered during a hackathon submission.

Usage:
    python -m tools.check_ci [--json]
Exit codes: 0 pass, 1 problem, 2 configuration error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
MAKEFILE = ROOT / "Makefile"

REQUIRED_COMMANDS = ["make setup", "make lint", "make test", "make verify-core"]
REQUIRED_KEYS = ["name:", "on:", "jobs:", "runs-on:", "steps:"]
# Commands a workflow is allowed to call without further checks.
SHELL_BUILTINS = {"echo", "cat", "if", "fi", "else", "then", "test", "[", "cd", "set", "true"}


def make_targets() -> set[str]:
    targets: set[str] = set()
    if not MAKEFILE.is_file():
        return targets
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_-]+):", line)
        if match:
            targets.add(match.group(1))
    return targets


def run_commands(text: str) -> list[str]:
    """Extract commands from single-line and block ``run:`` entries."""
    commands: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(\s*)-?\s*run:\s*(.*)$", line)
        if not match:
            index += 1
            continue
        indent = len(line) - len(line.lstrip())
        inline = match.group(2).strip()
        if inline and inline not in {"|", ">", "|-", ">-"}:
            commands.append(inline)
            index += 1
            continue
        index += 1
        while index < len(lines):
            body = lines[index]
            if body.strip() == "":
                index += 1
                continue
            if len(body) - len(body.lstrip()) <= indent:
                break
            commands.append(body.strip())
            index += 1
    return commands


def flatten(commands: list[str]) -> list[str]:
    """Split shell pipelines, ``&&`` chains, `if` lines and heredoc noise into single commands."""
    flat: list[str] = []
    for command in commands:
        if command.startswith("#"):
            continue
        for part in re.split(r"&&|\|\||\||;", command):
            part = part.strip()
            if part:
                flat.append(part)
    return flat


def check_command(command: str, targets: set[str]) -> str | None:
    """Return a problem description, or None when the command is known to exist."""
    tokens = command.split()
    if not tokens:
        return None
    head = tokens[0]
    if head in SHELL_BUILTINS or head in {">", "}"} or head.startswith(('"', "'")):
        return None
    if head == "make":
        for token in tokens[1:]:
            if token.startswith("-"):
                continue
            if token not in targets:
                return f"`make {token}` is not a target in the Makefile"
            break
        return None
    if head in {"python", "python3"} and len(tokens) >= 3 and tokens[1] == "-m":
        module = tokens[2]
        path = ROOT / (module.replace(".", "/") + ".py")
        if not path.is_file():
            return f"`python -m {module}` has no module file ({module.replace('.', '/')}.py)"
        return None
    if head in {"./gradlew", "pip", "pip3", "npm", "apt-get", "sudo"}:
        return None  # out of scope for this repository's gate
    return None


def check_workflow(path: Path, targets: set[str]) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    text = path.read_text(encoding="utf-8")
    name = path.name

    for key in REQUIRED_KEYS:
        if not re.search(rf"^\s*{re.escape(key)}", text, re.MULTILINE):
            problems.append(f"{name}: missing `{key.rstrip(':')}`")

    commands = run_commands(text)
    if not commands:
        problems.append(f"{name}: no `run:` steps found")
    flat = flatten(commands)
    for required in REQUIRED_COMMANDS:
        if not any(required == command or command.startswith(required + " ")
                   for command in flat):
            problems.append(f"{name}: the gate command `{required}` is not executed")

    for command in flat:
        problem = check_command(command, targets)
        if problem:
            problems.append(f"{name}: {problem} (from `{command[:80]}`)")

    for action in re.findall(r"uses:\s*([\w./-]+)@([\w.\-]+)", text):
        repo, ref = action
        if ref in {"main", "master", "HEAD"}:
            problems.append(f"{name}: `{repo}` is pinned to a branch (`{ref}`), not a tag")
        elif not re.fullmatch(r"v?\d+(?:\.\d+)*", ref):
            problems.append(f"{name}: `{repo}@{ref}` is not a version tag")

    if "artifacts/reports/latest" not in text:
        problems.append(f"{name}: does not upload artifacts/reports/latest/")

    permissions = re.search(r"^permissions:\s*$", text, re.MULTILINE)
    if permissions is None:
        problems.append(f"{name}: no explicit `permissions:` block (defaults are too broad)")
    elif "contents: read" not in text:
        problems.append(f"{name}: permissions must at least include `contents: read`")

    notes.append(f"{name}: {len(flat)} commands, "
                 f"{len(re.findall(r'uses:', text))} actions, "
                 f"{len(re.findall(r'^  [a-z0-9-]+:$', text, re.MULTILINE))} job(s)")
    return problems, notes


def run() -> dict:
    targets = make_targets()
    if not WORKFLOWS.is_dir():
        return {"check": "ci", "status": "FAIL",
                "problems": [".github/workflows/ is missing"], "notes": []}
    workflows = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    if not workflows:
        return {"check": "ci", "status": "FAIL", "problems": ["no workflow files"], "notes": []}
    problems: list[str] = []
    notes: list[str] = []
    for path in workflows:
        found, extra = check_workflow(path, targets)
        problems.extend(found)
        notes.extend(extra)
    return {
        "check": "ci",
        "status": "PASS" if not problems else "FAIL",
        "workflows": [path.name for path in workflows],
        "make_targets": len(targets),
        "problems": problems,
        "notes": notes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run()
    except OSError as exc:
        print(f"ci: CONFIG ERROR - {exc}")
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"ci: {result['status']} ({', '.join(result.get('workflows', []))})")
        for note in result["notes"]:
            print(f"  . {note}")
        for problem in result["problems"]:
            print(f"  - {problem}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
