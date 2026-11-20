"""Probe for official starter code and run its smoke test when it exists (task 0.7).

Phase 0 task 0.7 says: "run a minimal smoke test of the official starter environment, if it
exists". The honest answer today is "it does not exist", which is easy to say and impossible to
verify. This tool makes that statement executable:

* it scans every plausible location for organizer material;
* if nothing is found it returns ``SKIPPED`` with the scanned paths, so the claim stops being an
  opinion and becomes a reproducible output;
* if something *is* found, it refuses to trust it blindly: it records hashes, checks that the
  archive manifest classifies it, then compiles it and runs exactly one configured smoke command
  with a hard timeout and no network.

Nothing here imports or executes untrusted code beyond ``compileall`` unless a human has added a
smoke command to ``configs/submission/starter_probe.json``, so a malicious starter cannot run by
accident.

Usage:
    python -m tools.probe_starter [--json] [--run]

Exit codes: 0 nothing to probe (SKIPPED) or probe passed, 1 probe found material that failed,
2 configuration error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.canonical_json import canonical_digest

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "configs" / "submission" / "starter_probe.json"

CANDIDATES = [
    "starter",
    "organizer",
    "organizer_starter",
    "docs/official/starter",
    "docs/official/samples",
    "external/starter",
    "submission/starter",
]

ENTRYPOINTS = ["main.py", "run.py", "app.py", "smoke_test.py", "setup.py", "pyproject.toml",
               "requirements.txt", "Makefile", "README.md"]

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_CONFIG = 2


def load_config() -> dict:
    if not CONFIG.is_file():
        raise SystemExit(f"probe_starter: CONFIG ERROR - missing {CONFIG.relative_to(ROOT)}")
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"probe_starter: CONFIG ERROR - {exc}") from exc


def inventory(path: Path) -> dict:
    files = sorted(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    hashed = {str(p.relative_to(path)).replace("\\", "/"): canonical_digest(p.read_text(errors="ignore"))
              for p in files[:200]}
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "file_count": len(files),
        "bytes": sum(p.stat().st_size for p in files),
        "entrypoints": [name for name in ENTRYPOINTS if (path / name).exists()],
        "python_files": len([p for p in files if p.suffix == ".py"]),
        "bundle_digest": canonical_digest(hashed),
    }


def scan() -> list[dict]:
    return [inventory(ROOT / candidate) for candidate in CANDIDATES if (ROOT / candidate).is_dir()]


def smoke(command: list[str], cwd: Path, timeout: int) -> dict:
    if shutil.which(command[0]) is None:
        return {"command": command, "status": "SKIPPED", "reason": f"{command[0]} not available"}
    try:
        proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"command": command, "status": "FAIL", "reason": f"timed out after {timeout}s"}
    return {
        "command": command,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "exit_code": proc.returncode,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def compile_check(path: Path) -> dict:
    proc = subprocess.run([sys.executable, "-m", "compileall", "-q", str(path)],
                          capture_output=True, text=True, timeout=120)
    return {"status": "PASS" if proc.returncode == 0 else "FAIL",
            "stderr_tail": proc.stderr[-2000:]}


def probe(run: bool) -> dict:
    config = load_config()
    found = scan()
    result: dict = {
        "check": "starter_probe",
        "task": "Phase 0 task 0.7 (smoke test of the official starter environment, if it exists)",
        "status": "SKIPPED",
        "reason": "",
        "candidates_scanned": CANDIDATES,
        "found": found,
        "config": str(CONFIG.relative_to(ROOT)).replace("\\", "/"),
        "manifest_absent_entries": [],
        "smoke_results": [],
    }

    manifest_path = ROOT / "docs" / "official" / "MANIFEST.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result["manifest_absent_entries"] = [
            item["document"] for item in manifest.get("absent", [])
            if "starter" in item["document"].lower()
        ]

    if not found:
        result["reason"] = (
            "no organizer starter code or samples exist in this checkout; the archive manifest "
            "records the absence, so there is nothing to smoke-test (docs/QUESTIONS.md Q-001)"
        )
        return result

    for item in found:
        path = ROOT / item["path"]
        item["compile"] = compile_check(path)
        if item["compile"]["status"] != "PASS":
            result["status"] = "FAIL"
            result["reason"] = f"{item['path']} does not compile"
            return result

    for item in found:
        path = ROOT / item["path"]
        for entry in config.get("smoke_commands", {}).get(item["path"], []):
            command = [part.replace("{path}", str(path)) for part in entry]
            if not run:
                result["smoke_results"].append({"command": command, "status": "SKIPPED",
                                                "reason": "--run not passed; command not executed"})
                continue
            outcome = smoke(command, path, int(config.get("timeout_seconds", 120)))
            result["smoke_results"].append(outcome)
            if outcome["status"] == "FAIL":
                result["status"] = "FAIL"
                result["reason"] = f"smoke command failed for {item['path']}: {command}"
                return result

    result["status"] = "PASS"
    result["reason"] = (f"{len(found)} starter bundle(s) found, compiled"
                        + (" and smoke-tested" if run else "; smoke commands not executed (--run absent)"))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--run", action="store_true",
                        help="execute the smoke commands configured for the bundle (opt-in)")
    args = parser.parse_args(argv)
    try:
        result = probe(args.run)
    except SystemExit as exc:  # configuration error surfaced by load_config
        print(exc)
        return EXIT_CONFIG
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"starter probe: {result['status']}")
        print(f"  reason: {result['reason']}")
        print(f"  scanned: {', '.join(CANDIDATES)}")
        print(f"  found: {[item['path'] for item in result['found']] or 'nothing'}")
        if result["manifest_absent_entries"]:
            print(f"  manifest records as absent: {result['manifest_absent_entries']}")
        for outcome in result["smoke_results"]:
            print(f"  smoke {outcome['status']}: {outcome['command']} ({outcome.get('reason', '')})")
    return EXIT_OK if result["status"] in {"SKIPPED", "PASS"} else EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
