#!/usr/bin/env python3
"""Local offline isolation check (approximation, NOT a Docker build).

The Docker offline gate (``make docker-offline`` / CI ``docker-offline`` job)
verifies the *image*: Dockerfile, .dockerignore, entrypoint, non-root uid.
This repository cannot build that image locally everywhere (no container
runtime on this host), so this tool provides the closest honest local
equivalent:

  1. Creates a user+network+mount namespace (``unshare -rmn``): no network
     route exists in the namespace, and the source tree is bind-mounted
     READ-ONLY with only ``artifacts/`` writable (tmpfs), mirroring the
     container's hardening flags (``--network=none``, ``--read-only``).
  2. Refuses to run if the network namespace can reach the outside.
  3. Refuses to run if the bound source tree is writable.
  4. Runs the full stdlib unittest suite (``python -m unittest discover``)
     with bytecode writing disabled (read-only rootfs safe).

What it PROVES: the test suite passes with zero network access and a
read-only source tree. What it does NOT prove: that the Docker image builds,
that .dockerignore excludes sealed paths at build-context level (that is
covered by tests/judge/test_release_audit.py::TestDockerIgnore and the CI
docker-offline job), or that the entrypoint behaves under Docker. The Docker
gate remains CI-authoritative; this tool is supporting local evidence.

Usage: python3 tools/offline_local_check.py [--keep]
Exit codes: 0 = isolated suite PASS, 1 = FAIL/violations, 2 = runtime missing.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INNER_MARKER = "_OFFLINE_CHECK_INNER"


def _inside_namespace() -> bool:
    return os.environ.get(INNER_MARKER) == "1"


def _inner() -> int:
    app = Path(sys.argv[2])
    # 1) network namespace must have no route out
    try:
        import socket

        socket.create_connection(("1.1.1.1", 53), timeout=3).close()
        print("OFFLINE CHECK FAIL: network namespace can reach 1.1.1.1:53")
        return 1
    except OSError:
        print("preflight: network namespace has no route (ok)")
    # 2) source tree must be read-only
    probe = app / ".offline_write_probe"
    try:
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        print("OFFLINE CHECK FAIL: source tree is writable inside the namespace")
        return 1
    except OSError:
        print("preflight: source tree is read-only (ok)")
    # 3) run the suite
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        cwd=app,
        env=env,
        text=True,
        capture_output=True,
    )
    tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-15:])
    print(tail)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="keep the mount dir (debug)")
    args = parser.parse_args()

    if _inside_namespace():
        return _inner()

    if not Path("/usr/bin/unshare").exists() and os.geteuid() != 0:
        print("unshare not available and not root; cannot create namespaces")
        return 2

    with tempfile.TemporaryDirectory(prefix="tl-offline-") as tmp:
        app = Path(tmp) / "app"
        app.mkdir()
        inner_env = dict(os.environ, **{INNER_MARKER: "1"})
        script = (
            f"mount --bind -o ro {REPO_ROOT} {app} && "
            f"mount -t tmpfs tmpfs {app}/artifacts && "
            f"exec {sys.executable} {REPO_ROOT / 'tools' / 'offline_local_check.py'} --inner {app}"
        )
        # NOTE: the inner interpreter re-runs this file with --inner; the
        # environment marker switches it into _inner() mode.
        inner_env["OFFLINE_CHECK_APP"] = str(app)
        proc = subprocess.run(
            ["unshare", "-rmn", "sh", "-c", script],
            env=inner_env,
            text=True,
        )
        print(f"offline namespace run exit code: {proc.returncode}")
        if args.keep:
            print(f"mount dir kept for debugging at {tmp} (leaks namespace mounts)")
        return proc.returncode


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--inner":
        sys.exit(_inner())
    sys.exit(main())
