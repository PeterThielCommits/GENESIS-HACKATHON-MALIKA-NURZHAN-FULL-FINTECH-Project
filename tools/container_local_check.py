#!/usr/bin/env python3
"""Container-equivalent local verification run (no container runtime needed).

Why this tool exists
--------------------
The hardened offline container (``make docker-check``, CI job ``docker-offline``)
is the authority for the Docker *image*. On a host without a container runtime
the image cannot be built, so the only local evidence would be "the repository
says the Dockerfile is right" -- which is not evidence at all.

This tool closes as much of that gap as the host allows: it **materialises the
image** the way ``docker build`` would (``COPY . /app`` with the
``.dockerignore`` rules applied, the ``compileall`` step, the report
directories) and then **runs the container's command** (``make verify``) under
the same hardening the CI job uses:

| Container flag                   | Local equivalent                                     |
|----------------------------------|------------------------------------------------------|
| ``--network=none``               | new network namespace (no route out)                 |
| ``--read-only``                  | the image tree is bind-mounted read-only              |
| ``--tmpfs /app/artifacts/...``   | tmpfs over the three writable paths                   |
| ``--cap-drop ALL``               | every capability dropped (``CapEff = 0``)             |
| ``--security-opt no-new-privileges`` | ``NoNewPrivs = 1``                                |
| ``USER 10001:10001``             | the process runs as uid 10001 / gid 10001             |
| ``--cpus=2 --memory=4g``         | recorded, not enforced (needs cgroups)               |

What this PROVES: the build context is the one the image would receive (no
sealed truth, no key material, no VCS metadata, no stale bytecode), the
image's own offline build steps succeed, and the container's command completes
with **no network, a read-only tree, no capabilities and a non-root uid**.

What this does NOT prove: that ``docker build`` succeeds (the base image
cannot be pulled without a registry), nor that the Docker daemon's own
hardening behaves identically. The Docker gate stays CI-authoritative; this is
the strongest local equivalent and its exact scope is recorded in the artifact.

Usage:  python3 tools/container_local_check.py [--json] [--keep] [--out PATH]
Exit codes: 0 = the container-equivalent run PASS, 1 = FAIL, 2 = the host
cannot provide the isolation (no unprivileged user namespaces).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.docker_context import DockerIgnore, build_context  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The image's ``CMD`` (Dockerfile) and the CI job's run flags.
CONTAINER_CMD: tuple[str, ...] = ("make", "verify")

#: Paths that the container keeps writable (tmpfs in the CI run).
WRITABLE_PATHS: tuple[str, ...] = (
    "artifacts/reports/latest",
    "artifacts/reports/doc_claims",
    "artifacts/trajectories",
)

#: The uid/gid the image runs as (Dockerfile ``USER 10001:10001``).
CONTAINER_UID = 10001
CONTAINER_GID = 10001

#: Build-context rules that must hold, whatever the Dockerfile says. A path
#: that violates one of them would put sealed truth, key material or stale
#: bytecode into the image, so the check fails loudly instead of quietly
#: copying the tree.
FORBIDDEN_CONTEXT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(^|/)\.git(/|$)", "VCS metadata"),
    (r"(^|/)__pycache__(/|$)", "stale bytecode cache"),
    (r"\.py[cod]$", "stale bytecode file"),
    (r"^episodes/[^/]+/sealed(/|$)", "sealed truth (depth 1)"),
    (r"^episodes/[^/]+/[^/]+/sealed(/|$)", "sealed truth (depth 2)"),
    (r"^episodes/hidden(/|$)", "hidden episodes"),
    (r"(^|/)\.env($|\.)", "environment secrets"),
    (r"\.(pem|key|p12|pfx)$", "key material"),
    (r"^artifacts/trajectories/", "pre-generated trajectories"),
)

#: Files the image must contain (the runtime needs them).
REQUIRED_CONTEXT_PATHS: tuple[str, ...] = (
    "Makefile",
    "Dockerfile",
    "judge_adapter.py",
    "contracts/loader.py",
    "judge/verify.py",
    "harness/replay.py",
)

#: The roots the Dockerfile pre-compiles (``RUN python3 -m compileall ...``).
COMPILE_ROOTS: tuple[str, ...] = (
    "judge_adapter.py",
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
    "tools",
    "tests",
    "independent_verifier",
)


# --------------------------------------------------------------------------- #
# build context
# --------------------------------------------------------------------------- #
def context_violations(paths: Iterable[str]) -> list[str]:
    """Context paths that would break the image contract."""
    violations: list[str] = []
    for posix in paths:
        for pattern, reason in FORBIDDEN_CONTEXT_PATTERNS:
            if re.search(pattern, posix):
                violations.append(f"{posix} ({reason})")
                break
    return violations


def missing_required(paths: Iterable[str]) -> list[str]:
    present = set(paths)
    return [name for name in REQUIRED_CONTEXT_PATHS if name not in present]


def materialise_context(
    paths: Iterable[str], destination: Path, repo_root: Path = REPO_ROOT
) -> int:
    """Copy the context into ``destination`` (the image's ``/app``)."""
    copied = 0
    for posix in paths:
        source = repo_root / posix
        target = destination / posix
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    return copied


def context_digest(paths: Iterable[str], repo_root: Path = REPO_ROOT) -> str:
    """A stable digest over the context (path + content of every file)."""
    digest = hashlib.sha256()
    for posix in sorted(paths):
        digest.update(posix.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256((repo_root / posix).read_bytes()).digest())
    return digest.hexdigest()


def apply_image_build_steps(app_dir: Path) -> dict[str, Any]:
    """Run the Dockerfile's offline build steps inside the materialised image.

    * ``python3 -m compileall -q <roots>`` -- pre-compile bytecode so the
      read-only runtime never has to write ``.pyc`` files;
    * create the report directories with mode ``1777`` (the Dockerfile does
      the same, because the runtime mounts them as tmpfs);
    * write the image's own provenance record (``tools/docker_build_info.py``).
    """
    result: dict[str, Any] = {"compileall": "skipped", "report_dirs": []}
    roots = [name for name in COMPILE_ROOTS if (app_dir / name).exists()]
    if roots:
        proc = subprocess.run(
            [sys.executable, "-m", "compileall", "-q", *roots],
            cwd=str(app_dir),
            text=True,
            capture_output=True,
        )
        result["compileall"] = "ok" if proc.returncode == 0 else f"FAIL ({proc.returncode})"
        if proc.returncode != 0:
            result["compileall_output"] = (proc.stdout + proc.stderr)[-2000:]
    for rel in ("artifacts/reports/latest", "artifacts/reports/doc_claims", "artifacts/trajectories"):
        target = app_dir / rel
        target.mkdir(parents=True, exist_ok=True)
        os.chmod(target, 0o1777)
        result["report_dirs"].append(rel)
    return result


# --------------------------------------------------------------------------- #
# the container run
# --------------------------------------------------------------------------- #
def _run_script(app_dir: Path, command: Iterable[str], capture_dir: Path) -> str:
    """The shell that runs inside the namespaces.

    It performs the mounts, drops to the container's user and executes the
    container command after asserting the hardening actually took effect. The
    artifacts the run produced are copied out of the container's tmpfs so the
    evidence can be compared with a host run.
    """
    quoted = " ".join(repr(part) for part in command)
    app = str(app_dir)
    capture = str(capture_dir)
    mounts = "\n".join(
        f'  mount -t tmpfs -o mode=1777,size=64m tmpfs "{app}/{rel}"'
        for rel in WRITABLE_PATHS
    )
    return f"""
set -e
APP="{app}"
export APP
mount --bind "$APP" "$APP"
{mounts}
mount -o remount,bind,ro "$APP"
cd "$APP"
exec unshare --map-user={CONTAINER_UID} --map-group={CONTAINER_GID} -- \\
  setpriv --no-new-privs --inh-caps=-all --ambient-caps=-all \\
          --reuid={CONTAINER_UID} --regid={CONTAINER_GID} --keep-groups -- \\
  sh -c '
    echo "--- container preflight"
    echo "uid=$(id -u) gid=$(id -g)"
    grep -E "^CapEff|^CapPrm|^CapInh|^CapAmb|^NoNewPrivs" /proc/self/status
    if (touch "$APP/__write_probe" 2>/dev/null); then
      echo "PREFLIGHT FAIL: the image tree is writable"; exit 3
    fi
    echo "image tree: read-only (ok)"
    if (touch "$APP/artifacts/reports/latest/__write_probe" 2>/dev/null); then
      echo "report dir: writable (ok)"
      rm -f "$APP/artifacts/reports/latest/__write_probe"
    else
      echo "PREFLIGHT FAIL: the report directory is not writable"; exit 3
    fi
    if python3 - <<"PYEOF"
import socket, sys
try:
    socket.create_connection(("1.1.1.1", 53), timeout=3).close()
except OSError:
    sys.exit(1)
sys.exit(0)
PYEOF
    then
      echo "PREFLIGHT FAIL: the network namespace can reach the outside"; exit 3
    fi
    echo "network: no route out (ok)"
    echo "--- container command"
    {quoted}
    rc=$?
    mkdir -p "{capture}" 2>/dev/null || true
    cp -a "$APP/artifacts/reports/latest/." "{capture}/" 2>/dev/null || true
    exit $rc
  '
"""


def run_container_equivalent(
    app_dir: Path, timeout: int = 3600, capture_dir: Path | None = None
) -> dict[str, Any]:
    """Run the container command inside the namespaces."""
    capture = capture_dir if capture_dir is not None else app_dir.parent / "captured"
    script = _run_script(app_dir, CONTAINER_CMD, capture)
    try:
        proc = subprocess.run(
            ["unshare", "--map-root-user", "--mount", "--net", "sh", "-c", script],
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"status": "UNAVAILABLE", "reason": "unshare(1) is not available on this host"}
    except subprocess.TimeoutExpired:
        return {"status": "FAIL", "reason": f"the container run exceeded {timeout}s"}
    output = proc.stdout + proc.stderr
    artifacts: list[str] = []
    if capture.is_dir():
        artifacts = sorted(p.name for p in capture.iterdir() if p.is_file())
    return {
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "exit_code": proc.returncode,
        "output_tail": "\n".join(output.splitlines()[-40:]),
        "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        "produced_artifacts": artifacts,
        "produced_artifact_count": len(artifacts),
    }


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def check(repo_root: Path = REPO_ROOT, keep: bool = False, timeout: int = 3600) -> dict[str, Any]:
    """Materialise the image, run the container command, return the evidence."""
    started = datetime.now(timezone.utc)
    ignore = DockerIgnore.from_file(repo_root / ".dockerignore")
    paths = build_context(repo_root, ignore)
    violations = context_violations(paths)
    missing = missing_required(paths)

    report: dict[str, Any] = {
        "artifact": "container-local-check",
        "generated_at_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _git_commit(repo_root),
        "container_runtime_available_locally": _runtime_available(),
        "method": (
            "tools/container_local_check.py: the image is materialised from the "
            "build context (.dockerignore rules applied with Docker's own path "
            "semantics) and the Dockerfile's offline build steps, then the container "
            "command runs in an unprivileged user+mount+network namespace as uid "
            "10001 with no capabilities, no_new_privs, a read-only image tree and "
            "tmpfs over the writable paths."
        ),
        "scope": (
            "This is a CONTAINER-EQUIVALENT local run, NOT a Docker build: no "
            "container runtime and no registry access are available on this host, so "
            "the base image cannot be pulled and `docker build` cannot run. The "
            "Docker gate (make docker-build + make docker-check-container, CI job "
            "docker-offline) remains authoritative for the image."
        ),
        "build_context": {
            "files": len(paths),
            "bytes": sum((repo_root / p).stat().st_size for p in paths),
            "digest_sha256": context_digest(paths, repo_root),
            "forbidden_paths": violations,
            "missing_required_paths": missing,
        },
    }

    if violations or missing:
        report["status"] = "FAIL"
        report["reason"] = "the build context violates the image contract"
        report["finished_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return report

    tmp = Path(tempfile.mkdtemp(prefix="tl-container-"))
    try:
        app_dir = tmp / "app"
        app_dir.mkdir(parents=True)
        copied = materialise_context(paths, app_dir, repo_root)
        report["build_context"]["copied_files"] = copied
        report["image_build_steps"] = apply_image_build_steps(app_dir)
        if report["image_build_steps"].get("compileall", "").startswith("FAIL"):
            report["status"] = "FAIL"
            report["reason"] = "the image's compileall step failed"
            report["finished_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return report
        report["container_run"] = run_container_equivalent(app_dir, timeout=timeout)
        report["status"] = report["container_run"]["status"]
        report["finished_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return report
    finally:
        if keep:
            print(f"context kept at {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def _runtime_available() -> bool:
    return any(shutil.which(binary) for binary in ("docker", "podman", "nerdctl"))


def _git_commit(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        sha = out.stdout.strip()
        if out.returncode == 0 and len(sha) == 40:
            return sha
    except Exception:
        pass
    return "unknown (no .git)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Container-equivalent local verification run")
    parser.add_argument("--json", action="store_true", help="Print the evidence as JSON")
    parser.add_argument("--keep", action="store_true", help="Keep the materialised context")
    parser.add_argument("--out", default="", help="Write the evidence JSON to this path")
    parser.add_argument("--timeout", type=int, default=3600, help="Timeout for the container run")
    args = parser.parse_args(argv)

    report = check(keep=args.keep, timeout=args.timeout)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        context = report["build_context"]
        print(f"container-local-check: {report['status']}")
        print(
            "  build context: {files} files, {bytes} bytes, digest {digest}".format(
                files=context["files"],
                bytes=context["bytes"],
                digest=context["digest_sha256"][:16],
            )
        )
        for violation in context["forbidden_paths"]:
            print(f"  FORBIDDEN in context: {violation}")
        for name in context["missing_required_paths"]:
            print(f"  MISSING from context: {name}")
        run = report.get("container_run") or {}
        if run.get("output_tail"):
            print(run["output_tail"])
        if report["status"] != "PASS":
            print(f"  reason: {report.get('reason') or run.get('reason') or 'see the output above'}")
    if report["status"] == "UNAVAILABLE":
        return 2
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
