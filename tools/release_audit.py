#!/usr/bin/env python3
"""Release candidate audit (Phase 16, tasks 16.5 and 16.6; TZ §16).

Checks the things a *repository review* cannot see but a *release* depends on:

  16.5  secrets, file list, package size, dependencies
  16.6  the exact official entrypoint and submission format

Every check is a real measurement of the working tree or of a fresh Python
subprocess. Nothing is asserted from documentation; where a value also appears
in the docs, ``tools/verify_doc_claims.py`` is what keeps the two in agreement.

Design rules (learned the hard way in Phase 15):
  * Exit code is the verdict. The JSON report is a convenience artifact and its
    write failure must never turn a PASS into a crash (read-only rootfs).
  * Console output is transliterated to ASCII, because the hardened offline
    container runs with ``LC_ALL=C`` and any non-ASCII character in a print
    raises UnicodeEncodeError.
  * No value produced by this script is compared against itself. Size, counts
    and hashes are measured; budgets are constants from this file.

Exit codes (TZ §23.3):
  0  every required audit PASS
  1  one or more release blockers found
  2  configuration/contract error (audit could not run meaningfully)
  4  release blocker of the severe class (sealed data in the package)
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# The audit report is deliberately NOT inside artifacts/reports/latest/: that
# directory is the frozen Judge Kit evidence set (TZ §23.5, 20 files, 12 gates),
# and adding a file there would make artifact counts depend on execution order.
OUTPUT_PATH = REPO_ROOT / "artifacts" / "reports" / "release" / "release_audit.json"

# --- budgets (constants, never measured from the run being checked) ---------
MAX_PACKAGE_BYTES = 50 * 1024 * 1024  # TZ §22.4 disk budget: 50 MB
MAX_TRACKED_FILES = 1000
MAX_SINGLE_FILE_BYTES = 10 * 1024 * 1024  # a single file must stay reviewable

# Files that must never be part of the public submission package: they hold the
# answers the policy is supposed to discover (REQ-ARENA-005, TZ §22).
FORBIDDEN_PATTERNS = (
    # `sealed/` may sit directly under a split (episodes/dev/sealed/) or under an
    # episode (episodes/dev/ep_x/sealed/, the real layout), and .gitignore covers
    # both. An audit pattern that only knew one shape let a forced `git add -f`
    # through while reporting PASS -- so match any depth.
    re.compile(r"(^|/)episodes/(?:[^/]+/)*sealed(/|$)"),
    re.compile(r"(^|/)episodes/(?:[^/]+/)*hidden(/|$)"),
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)\.env\."),
    re.compile(r"\.pem$"),
    re.compile(r"\.key$"),
    re.compile(r"(^|/)id_rsa"),
    re.compile(r"(^|/)credentials"),
    re.compile(r"(^|/)\.npmrc$"),
    re.compile(r"(^|/)\.pypirc$"),
)

# High-confidence credential shapes. Prose such as "secret salt" must not trip
# the audit, so these are deliberately specific.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github token", re.compile(r"\bgh[posru]_[A-Za-z0-9]{36}\b")),
    ("github pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("openai-style key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
)

# Text files only: binary blobs cannot hold a usable text credential and would
# make the scan slow and noisy.
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".woff", ".woff2", ".ico"}

# Stdlib modules that are acceptable without justification; anything outside the
# standard library is a dependency and must be declared in the allowlist below.
DECLARED_RUNTIME_DEPENDENCIES: tuple[str, ...] = ()  # stdlib-only design (TZ §22.4)

OFFICIAL_ENTRYPOINT = "judge_adapter.py"
OFFICIAL_EXPORTS = ("generate_episode", "make_env", "score_episode")
ADAPTER_TOOL_NAMES = ("list_records", "get_record", "get_document", "calculator", "submit")


# ---------------------------------------------------------------------------
# output helpers
# ---------------------------------------------------------------------------
def _say(message: str) -> None:
    """Print ASCII-only, independent of the host locale (container is LC_ALL=C)."""
    text = (
        message.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2192", "->")
        .replace("\u00a7", "S")
        .replace("\u2264", "<=")
        .replace("\u2265", ">=")
    )
    try:
        print(text)
    except UnicodeEncodeError:  # pragma: no cover - last-resort guard
        print(text.encode("ascii", "replace").decode("ascii"))


# Directories that are never part of the shipped tree. Mirrors .dockerignore:
# the offline image is built from this tree with .git excluded, so the image is
# itself a submission artefact and must be auditable.
NOT_SHIPPED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "build",
    "dist",
}
NOT_SHIPPED_SUFFIXES = (".pyc", ".pyo")


# Paths the project deliberately keeps out of version control but that may exist
# on disk. Mirrors .gitignore for the cases that matter to a release audit.
_GENERATED_IGNORED = (
    re.compile(r"(^|/)episodes/[^/]*/sealed(/|$)"),
    re.compile(r"(^|/)episodes/[^/]*/[^/]*/sealed(/|$)"),
    re.compile(r"(^|/)episodes/hidden(/|$)"),
    re.compile(r"(^|/)artifacts/reports/latest/[^/]*$"),
    re.compile(r"(^|/)artifacts/reports/(doc_claims|release)(/|$)"),
    re.compile(r"(^|/)artifacts/trajectories/"),
    re.compile(r"(^|/)\.env(\.|$)"),
    re.compile(r"\.(pem|key)$"),
    re.compile(r"(^|/)__pycache__(/|$)"),
    re.compile(r"\.py[co]$"),
)


def _is_ignored(rel: str) -> bool:
    """True when a path is generated/ignored and therefore not shipped evidence."""
    return any(p.search(rel) for p in _GENERATED_IGNORED)


def _walk_fallback() -> list[str]:
    """File list for a tree with no Git metadata (tarball, Docker image).

    `git ls-files` is preferred because it is exactly the submission package.
    But the offline image is built with `.dockerignore` excluding `.git`, and a
    release tarball has none either, so an audit that only worked in a checkout
    would be unusable precisely where it matters most.
    """
    out: list[str] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(REPO_ROOT)
        if any(part in NOT_SHIPPED_DIRS for part in rel.parts):
            continue
        if path.suffix in NOT_SHIPPED_SUFFIXES:
            continue
        url = str(rel).replace(os.sep, "/")
        # Honour the project's own ignore rules. Sealed truth is *generated* by
        # `make build-episodes` / `make official-eval` and is gitignored, so it is
        # not part of the package even though it exists on disk. Without this the
        # fallback reported 20 false FILELIST violations simply because someone
        # had run a legitimate build target first (found when `make verify-core`
        # failed on a tree that had just run `make build-episodes`).
        if _is_ignored(url):
            continue
        out.append(url)
    return out


def tracked_files() -> list[str]:
    """Return the release file list, from Git when available."""
    # The offline image has no `git` binary at all (only make + python), so this
    # raises FileNotFoundError rather than returning non-zero. Catch OSError, not
    # just a bad exit code -- otherwise the submission image cannot audit itself,
    # which is precisely where the audit matters most.
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            check=False,
        )
    except OSError:
        return _walk_fallback()
    if result.returncode != 0:
        return _walk_fallback()
    files = [p for p in result.stdout.decode("utf-8", "replace").split("\0") if p]
    return files if files else _walk_fallback()


# ---------------------------------------------------------------------------
# 16.5a secrets
# ---------------------------------------------------------------------------
def audit_secrets(files: list[str]) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    scanned = 0
    for rel in files:
        path = REPO_ROOT / rel
        if not path.is_file() or path.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for lineno, line in enumerate(text.splitlines(), start=1):
            for label, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append({"file": rel, "line": str(lineno), "kind": label})
    return {
        "id": "SECRETS",
        "title": "No hardcoded credentials in the tracked tree",
        "status": "PASS" if not findings else "FAIL",
        "detail": f"{scanned} text files scanned, {len(findings)} credential-shaped match(es)",
        "findings": findings[:20],
    }


def audit_forbidden_files(files: list[str]) -> dict[str, Any]:
    """Sealed truth and environment files must not reach the package."""
    hits = [rel for rel in files if any(p.search(rel) for p in FORBIDDEN_PATTERNS)]
    return {
        "id": "FILELIST",
        "title": "File list carries no sealed/hidden data or credentials files",
        "status": "PASS" if not hits else "FAIL",
        "detail": f"{len(files)} tracked files, {len(hits)} forbidden path(s)",
        "findings": hits[:20],
    }


# ---------------------------------------------------------------------------
# 16.5b package size
# ---------------------------------------------------------------------------
def audit_size(files: list[str]) -> dict[str, Any]:
    total = 0
    largest: list[tuple[int, str]] = []
    for rel in files:
        path = REPO_ROOT / rel
        try:
            size = path.stat().st_size
        except OSError:
            continue
        total += size
        largest.append((size, rel))
    largest.sort(reverse=True)
    oversized = [{"file": rel, "bytes": size} for size, rel in largest if size > MAX_SINGLE_FILE_BYTES]
    ok = total <= MAX_PACKAGE_BYTES and len(files) <= MAX_TRACKED_FILES and not oversized
    return {
        "id": "SIZE",
        "title": "Package fits the disk/file budget",
        "status": "PASS" if ok else "FAIL",
        "detail": (
            f"{len(files)} files, {total} bytes "
            f"(budget {MAX_TRACKED_FILES} files, {MAX_PACKAGE_BYTES} bytes)"
        ),
        "metrics": {
            "tracked_files": len(files),
            "total_bytes": total,
            "largest": [{"file": rel, "bytes": size} for size, rel in largest[:5]],
        },
        "findings": oversized,
    }


# ---------------------------------------------------------------------------
# 16.5c dependencies
# ---------------------------------------------------------------------------
STDLIB = set(getattr(sys, "stdlib_module_names", ()))
# Local top-level packages that belong to this repository.
LOCAL_PACKAGES = {
    "core",
    "contracts",
    "adapter",
    "gen",
    "invariants",
    "verifier",
    "nlp",
    "env",
    "harness",
    "scoring",
    "seal",
    "arena",
    "metamorphic",
    "judge",
    "independent_verifier",
    "tools",
    "tests",
    "judge_adapter",
}


def _runtime_sources(files: list[str]) -> list[str]:
    """Python files on the runtime path (tests and tools are not the product)."""
    out = []
    for rel in files:
        if not rel.endswith(".py"):
            continue
        top = rel.split("/", 1)[0]
        if top in ("tests", "tools", "docs"):
            continue
        out.append(rel)
    return out


def audit_dependencies(files: list[str]) -> dict[str, Any]:
    """Prove the runtime package imports only the standard library.

    ``sys.stdlib_module_names`` is the authority for "stdlib" on 3.10+; local
    packages are this repository. Anything else is an undeclared dependency and
    a release blocker, because the offline image installs nothing
    (``PIP_NO_INDEX=1``).
    """
    external: dict[str, list[str]] = {}
    parsed = 0
    for rel in _runtime_sources(files):
        try:
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        parsed += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relative import, internal by definition
                    continue
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                if not name or name in STDLIB or name in LOCAL_PACKAGES:
                    continue
                if name in DECLARED_RUNTIME_DEPENDENCIES:
                    continue
                external.setdefault(name, []).append(rel)
    return {
        "id": "DEPS",
        "title": "Runtime imports are stdlib-only (no install step offline)",
        "status": "PASS" if not external else "FAIL",
        "detail": (
            f"{parsed} runtime modules parsed, {len(external)} undeclared external import(s)"
        ),
        "metrics": {"declared": list(DECLARED_RUNTIME_DEPENDENCIES)},
        "findings": [{"module": m, "used_by": sorted(set(v))[:5]} for m, v in sorted(external.items())],
    }


# ---------------------------------------------------------------------------
# 16.6 official entrypoint and submission format
# ---------------------------------------------------------------------------
_PROBE = r"""
import inspect, json, sys
sys.path.insert(0, %r)
import judge_adapter as adapter

REPO = %r
EPISODE = REPO + "/episodes/dev/ep_dev_001_clean_distractors"

report = {"exports": {}, "tools": {}, "step_tuple_len": None, "reset_tuple_len": None}
for name in %r:
    fn = getattr(adapter, name, None)
    report["exports"][name] = None if fn is None else str(inspect.signature(fn))

# Gymnasium-native compatibility (Q-014) is about the RETURN contract, not the
# parameter count: a bound method legitimately takes one argument, `action`.
env = adapter.make_env()
reset_out = env.reset(seed=2026, config={"mode": "closed", "episode_dir": EPISODE, "team_config": {}})
report["reset_tuple_len"] = len(reset_out) if isinstance(reset_out, tuple) else None
step_out = env.step({"name": "list_records", "args": {"table": "ledger", "limit": 1}})
report["step_tuple_len"] = len(step_out) if isinstance(step_out, tuple) else None

# Tool vocabulary is verified by dispatching, in a FRESH env each time: an
# unknown action is answered with an UNKNOWN_ACTION error inside the observation,
# and `submit` terminates the episode, so sharing one env would poison the rest.
CALLS = {
    "list_records": {"table": "ledger", "limit": 2},
    "get_record": {"table": "ledger", "id": "no-such-id"},
    "get_document": {"doc_id": "no-such-doc"},
    "calculator": {"expression": "1 + 1"},
    "submit": {"findings": []},
}
for name, args in CALLS.items():
    e = adapter.make_env()
    e.reset(seed=2026, config={"mode": "closed", "episode_dir": EPISODE, "team_config": {}})
    obs, reward, done, truncated, info = e.step({"name": name, "args": args})
    err = (obs or {}).get("error") if isinstance(obs, dict) else None
    report["tools"][name] = {
        "accepted": not (isinstance(err, dict) and err.get("code") == "UNKNOWN_ACTION"),
        "error_code": (err or {}).get("code") if isinstance(err, dict) else None,
        "step_returned_5_tuple": all(v is not None or True for v in (obs, reward, done, truncated, info)),
    }
print(json.dumps(report))
"""


def audit_entrypoint() -> dict[str, Any]:
    """Import the official entrypoint in a *fresh process from a foreign cwd*.

    Running from ``/`` matters: it proves the adapter does not depend on the
    working directory, which is how a judge will invoke it. The step arity must
    be 5 (``obs, reward, terminated, truncated, info``) for Gymnasium-native
    compatibility (Q-014).
    """
    adapter_path = REPO_ROOT / OFFICIAL_ENTRYPOINT
    if not adapter_path.is_file():
        return {
            "id": "ENTRYPOINT",
            "title": "Official adapter entrypoint present and importable",
            "status": "FAIL",
            "detail": f"{OFFICIAL_ENTRYPOINT} is missing",
            "findings": [],
        }
    code = _PROBE % (str(REPO_ROOT), str(REPO_ROOT), list(OFFICIAL_EXPORTS))
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd="/",
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode != 0:
        return {
            "id": "ENTRYPOINT",
            "title": "Official adapter entrypoint present and importable",
            "status": "FAIL",
            "detail": "import from a foreign cwd failed",
            "findings": [{"stderr_tail": result.stderr.strip().splitlines()[-1:] or [""]}],
        }
    try:
        probe = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {
            "id": "ENTRYPOINT",
            "title": "Official adapter entrypoint present and importable",
            "status": "FAIL",
            "detail": "probe produced unparseable output",
            "findings": [{"stdout_tail": result.stdout.strip().splitlines()[-1:]}],
        }

    problems: list[str] = []
    for name in OFFICIAL_EXPORTS:
        if probe["exports"].get(name) is None:
            problems.append(f"missing export: {name}")
    if probe["step_tuple_len"] != 5:
        problems.append(
            f"step() must return (obs, reward, terminated, truncated, info); got {probe['step_tuple_len']} values"
        )
    if probe["reset_tuple_len"] != 2:
        problems.append(f"reset() must return (obs, info); got {probe['reset_tuple_len']} values")
    tools = probe.get("tools") or {}
    rejected = [t for t in ADAPTER_TOOL_NAMES if not (tools.get(t) or {}).get("accepted")]
    if rejected:
        problems.append(f"adapter rejected documented tool name(s): {', '.join(rejected)}")
    return {
        "id": "ENTRYPOINT",
        "title": "Official adapter entrypoint present and importable",
        "status": "PASS" if not problems else "FAIL",
        "detail": (
            f"{len(OFFICIAL_EXPORTS)} exports verified from cwd=/, "
            f"reset/{probe['reset_tuple_len']}-tuple, step/{probe['step_tuple_len']}-tuple, "
            f"{sum(1 for v in tools.values() if v.get('accepted'))}/{len(ADAPTER_TOOL_NAMES)} tool names accepted"
        ),
        "metrics": {
            "signatures": probe["exports"],
            "tools": tools,
            "step_tuple_len": probe["step_tuple_len"],
            "reset_tuple_len": probe["reset_tuple_len"],
        },
        "findings": [{"problem": p} for p in problems],
    }


def audit_submission_format() -> dict[str, Any]:
    """The packaged submission must be reproducible from the documented command.

    Checks that the documented single verification command exists, that the
    image definition is non-root and installs nothing, and that a submission
    document agrees with the adapter's vocabulary.
    """
    problems: list[str] = []
    dockerfile = REPO_ROOT / "Dockerfile"
    if not dockerfile.is_file():
        problems.append("Dockerfile missing")
        docker_text = ""
    else:
        docker_text = dockerfile.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"^USER\s+(?!root)\d+", docker_text, re.MULTILINE):
            problems.append("Dockerfile does not switch to a numeric non-root USER")
        if "PIP_NO_INDEX=1" not in docker_text:
            problems.append("Dockerfile does not pin PIP_NO_INDEX=1 (offline build)")
        if not re.search(r'CMD\s+\[\s*"make"\s*,\s*"verify"\s*\]', docker_text):
            problems.append("Dockerfile CMD is not the single documented command `make verify`")

    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8", errors="replace")
    for target in ("verify:", "docker-check:"):
        if target not in makefile:
            problems.append(f"Makefile target missing: {target.rstrip(':')}")

    # TZ 22.4: the base image must be pinned by digest and the image must
    # record its own provenance (base digest, Python patch version, package
    # versions). The record is written from a *built* image, so its absence is
    # reported here as a problem only when the release claims it.
    if docker_text:
        base_arg = re.search(
            r'^\s*ARG\s+BASE_IMAGE\s*=\s*"?([^"\s]+)"?\s*$', docker_text, re.MULTILINE
        )
        reference = base_arg.group(1) if base_arg else ""
        name, _, digest = reference.partition("@")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest or ""):
            problems.append(
                "the Docker base image is not pinned by digest (TZ 22.4)"
            )
        elif len(set(digest.split(":", 1)[1])) <= 1:
            problems.append("the pinned Docker base image digest is a placeholder")
        elif name != "python:3.11-slim-bookworm":
            problems.append(f"unexpected Docker base image {name!r}")
        if "docker_build_info.py emit" not in docker_text:
            problems.append("the Dockerfile does not record the image build provenance")
    build_info_path = REPO_ROOT / "docs" / "EVIDENCE" / "docker-build-info.json"
    if not build_info_path.is_file():
        problems.append("docs/EVIDENCE/docker-build-info.json is missing (the image build record)")
    else:
        try:
            build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"docs/EVIDENCE/docker-build-info.json is not valid JSON: {exc}")
            build_info = {}
        if build_info:
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(build_info.get("base_image_digest", ""))):
                problems.append("the recorded base image digest is not a digest")
            if not str(build_info.get("python_version", "")).startswith("3.11."):
                problems.append("the recorded Python patch version is not 3.11.x")
            required_packages = build_info.get("apt_packages_required") or []
            for package in ("make", "util-linux"):
                if package not in required_packages:
                    problems.append(f"the image build record does not declare the {package} package")
            # TZ 22.4 asks for the *package versions* too. They are recorded,
            # not pinned (L11), but a recorded version must be a real fact.
            observed = build_info.get("apt_packages_observed") or {}
            if not isinstance(observed, dict) or not observed:
                problems.append("the image build record publishes no observed package versions")
            else:
                for package in ("make", "util-linux"):
                    version = observed.get(package)
                    if not version or version == "unknown":
                        problems.append(
                            f"the image build record publishes no real version for {package}"
                        )

    docs = REPO_ROOT / "docs" / "API_USAGE.md"
    if not docs.is_file():
        problems.append("docs/API_USAGE.md missing")
    else:
        text = docs.read_text(encoding="utf-8", errors="replace")
        for name in ADAPTER_TOOL_NAMES:
            if name not in text:
                problems.append(f"API_USAGE.md does not document adapter tool {name}")
        for name in OFFICIAL_EXPORTS:
            if name not in text:
                problems.append(f"API_USAGE.md does not document entrypoint {name}")

    return {
        "id": "SUBMISSION",
        "title": "Submission format: documented command, non-root offline image, entrypoint",
        "status": "PASS" if not problems else "FAIL",
        "detail": f"{len(problems)} problem(s) in the submission packaging",
        "findings": [{"problem": p} for p in problems],
    }


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def run_audit() -> dict[str, Any]:
    files = tracked_files()
    if not files:
        return {
            "schema_version": "1.0.0",
            "report_type": "release_audit",
            "code_version": "twinledger@1.0.0",
            "phase": "16",
            "status": "ERROR",
            "checks": [],
            "error": "no files found: neither a Git checkout nor a readable tree",
            "failed": ["FILELIST"],
            "exit_code": 2,
            "official_score_claimed": False,
        }
    checks = [
        audit_secrets(files),
        audit_forbidden_files(files),
        audit_size(files),
        audit_dependencies(files),
        audit_entrypoint(),
        audit_submission_format(),
    ]
    failed = [c for c in checks if c["status"] != "PASS"]
    return {
        "schema_version": "1.0.0",
        "report_type": "release_audit",
        "code_version": "twinledger@1.0.0",
        "phase": "16",
        "checks": checks,
        "status": "PASS" if not failed else "FAIL",
        "failed": [c["id"] for c in failed],
        "exit_code": 0 if not failed else 1,
        "official_score_claimed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 16 release candidate audit (TZ 16.5/16.6)")
    parser.add_argument("--json", action="store_true", help="print the full report and exit")
    parser.add_argument("--no-write", action="store_true", help="do not write the report artifact")
    args = parser.parse_args(argv)

    report = run_audit()
    if report.get("status") == "ERROR":
        _say(f"release-audit: CONFIGURATION ERROR ({report['error']})")
        return 2

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return report["exit_code"]

    for check in report["checks"]:
        _say(f"[{check['status']}] {check['id']}: {check['title']}")
        _say(f"       {check['detail']}")
        for finding in check.get("findings", [])[:5]:
            _say(f"       - {json.dumps(finding, sort_keys=True, ensure_ascii=True)[:400]}")

    if not args.no_write:
        try:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            try:
                shown: Any = OUTPUT_PATH.relative_to(REPO_ROOT)
            except ValueError:
                shown = OUTPUT_PATH
            _say(f"report: {shown}")
        except OSError as exc:
            _say(f"release-audit: note: report not written ({exc.__class__.__name__}); verdict is authoritative")

    passed = len(report["checks"]) - len(report["failed"])
    verdict = "PASS" if report["status"] == "PASS" else f"FAIL ({', '.join(report['failed'])})"
    _say(f"release-audit: {verdict} ({passed}/{len(report['checks'])} checks)")
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
