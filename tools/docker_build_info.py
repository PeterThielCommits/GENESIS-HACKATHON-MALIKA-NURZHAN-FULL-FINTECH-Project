#!/usr/bin/env python3
"""Base-image pinning, image provenance and digest-drift reporting (TZ 22.4).

Master TZ §22.4 requires the Docker build to be reproducible "as far as the
base image allows" and to pin **the base image digest, the Python patch
version, the package versions and the commands**.

This module is the single source of truth for that contract:

``emit``     run **inside the image** (see the ``Dockerfile``): writes the
             image's own provenance record -- base image + digest, the exact
             CPython patch version, the Debian release and the versions of the
             two Debian packages the image installs -- to
             ``/usr/local/share/twinledger/build_info.json``.

``verify``   run **anywhere** (no Docker needed): parses the ``Dockerfile``
             and the committed ``configs/docker_build_info.json`` and checks
             that the image is digest-pinned, that both files agree on the
             digest, and that the Python patch version and the package
             versions are recorded.

``resolve``  run **where Docker is available**: pulls the base tag, compares
             the tag's *current* digest with the pinned one and reports the
             drift. The pinned digest is what the image uses; a moved tag is
             reported (informational), never silently adopted.

The repository pins the base image by digest, so ``docker build`` always
produces the same userland. The two Debian packages are resolved by ``apt``
at build time, therefore their versions are *recorded* (in the image and in
``configs/docker_build_info.json``) and any drift is reported by ``resolve``
instead of breaking the build. See ``docs/LIMITATIONS.md`` (L11).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"
BUILD_INFO_PATH = REPO_ROOT / "docs" / "EVIDENCE" / "docker-build-info.json"

#: Where the image stores its own provenance record.
IMAGE_BUILD_INFO = "/usr/local/share/twinledger/build_info.json"

#: The base image this project is built on (Docker library, Debian bookworm).
EXPECTED_BASE_NAME = "python:3.11-slim-bookworm"

#: The Debian packages the image installs (TZ 22.4 "package versions").
TRACKED_APT_PACKAGES: tuple[str, ...] = ("make", "util-linux")

#: The Python minor version the project targets (TZ 22.1, 22.5).
EXPECTED_PYTHON_MINOR = (3, 11)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ARG_RE = re.compile(r'^\s*ARG\s+BASE_IMAGE\s*=\s*"?([^"\s]+)"?\s*$', re.MULTILINE)
_FROM_RE = re.compile(r"^\s*FROM\s+(\S+)\s*$", re.MULTILINE)

SCHEMA = "twinledger-build-info/v1"


# --------------------------------------------------------------------------- #
# Dockerfile parsing
# --------------------------------------------------------------------------- #
def parse_dockerfile(path: Path = DOCKERFILE) -> dict[str, Any]:
    """Extract the base image, its digest and the build-info emission step."""
    text = path.read_text(encoding="utf-8")
    arg_match = _ARG_RE.search(text)
    from_match = _FROM_RE.search(text)
    if arg_match is None:
        return {"error": "the Dockerfile does not declare `ARG BASE_IMAGE=...`"}
    if from_match is None:
        return {"error": "the Dockerfile has no FROM instruction"}
    raw = arg_match.group(1)
    from_value = from_match.group(1)
    name, _, digest = raw.partition("@")
    return {
        "base_image_arg": raw,
        "base_image_name": name,
        "base_image_digest": digest,
        "from_value": from_value,
        "uses_arg": from_value == "${BASE_IMAGE}",
        "emits_build_info": "docker_build_info.py emit" in text,
        "text": text,
    }


def base_image_is_pinned(parsed: dict[str, Any]) -> bool:
    """Whether the Dockerfile pins the base image by digest."""
    digest = parsed.get("base_image_digest") or ""
    return bool(_DIGEST_RE.match(digest))


def is_placeholder_digest(digest: str) -> bool:
    """Whether the digest is an obvious placeholder rather than a real one."""
    body = digest.split(":", 1)[-1]
    return len(set(body)) <= 1


# --------------------------------------------------------------------------- #
# emit (inside the image)
# --------------------------------------------------------------------------- #
def _dpkg_versions(packages: tuple[str, ...]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in packages:
        try:
            proc = subprocess.run(
                ["dpkg-query", "-W", "-f=${Version}", package],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            versions[package] = "unknown"
            continue
        value = proc.stdout.strip()
        versions[package] = value if proc.returncode == 0 and value else "unknown"
    return versions


def _os_release() -> str:
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    for line in text.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return "unknown"


def emit_build_info(base_image: str) -> dict[str, Any]:
    """Build the provenance record for the *current* (image) environment."""
    import platform

    name, _, digest = base_image.partition("@")
    version = platform.python_version()
    return {
        "schema": SCHEMA,
        "base_image": name,
        "base_image_digest": digest or "unknown",
        "python_version": version,
        "python_implementation": platform.python_implementation(),
        "python_build": " ".join(platform.python_build()),
        "os_release": _os_release(),
        "machine": platform.machine(),
        "apt_packages": _dpkg_versions(TRACKED_APT_PACKAGES),
        "apt_package_source": "resolved by apt at build time from the pinned base image",
    }


# --------------------------------------------------------------------------- #
# verify (static)
# --------------------------------------------------------------------------- #
def verify(require_pinned: bool = True, require_build_info: bool = False) -> dict[str, Any]:
    """Check the Dockerfile pinning and the committed build-info record.

    ``require_build_info`` escalates a missing ``configs/docker_build_info.json``
    from a warning to a failure. The release audit requires it; the ordinary
    lint does not, because the record is written from a *built* image.
    """
    problems: list[str] = []
    warnings: list[str] = []
    parsed = parse_dockerfile()
    if "error" in parsed:
        return {"status": "FAIL", "problems": [parsed["error"]], "warnings": [], "base_image": None}

    pinned = base_image_is_pinned(parsed)
    if not pinned:
        message = "the base image is not pinned by digest (TZ 22.4)"
        if require_pinned:
            problems.append(message)
        else:
            warnings.append(message)
    elif is_placeholder_digest(parsed["base_image_digest"]):
        problems.append("the pinned base image digest is a placeholder, not a real digest")
    elif not parsed["uses_arg"]:
        problems.append("the FROM instruction does not use ${BASE_IMAGE}")
    if parsed["base_image_name"] != EXPECTED_BASE_NAME:
        problems.append(
            f"unexpected base image {parsed['base_image_name']!r} (expected {EXPECTED_BASE_NAME!r})"
        )
    if not parsed["emits_build_info"]:
        problems.append("the Dockerfile does not emit the image build-info record")

    committed: dict[str, Any] | None = None
    if not BUILD_INFO_PATH.is_file():
        message = "docs/EVIDENCE/docker-build-info.json is missing"
        if require_build_info:
            problems.append(message)
        else:
            warnings.append(message)
    else:
        try:
            committed = json.loads(BUILD_INFO_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append("docs/EVIDENCE/docker-build-info.json is not valid JSON: {exc}")
    if committed is not None:
        if committed.get("schema") != SCHEMA:
            problems.append(f"unexpected build-info schema {committed.get('schema')!r}")
        if pinned and committed.get("base_image_digest") != parsed["base_image_digest"]:
            problems.append(
                "the committed build-info digest does not match the Dockerfile digest"
            )
        if pinned and committed.get("base_image") != parsed["base_image_name"]:
            problems.append("the committed build-info base image does not match the Dockerfile")
        python_version = str(committed.get("python_version", ""))
        parts = python_version.split(".")
        if len(parts) < 2 or tuple(int(p) for p in parts[:2]) != EXPECTED_PYTHON_MINOR:
            problems.append(
                f"the recorded Python version {python_version!r} is not "
                f"{EXPECTED_PYTHON_MINOR[0]}.{EXPECTED_PYTHON_MINOR[1]}.x"
            )
        declared = committed.get("apt_packages_required")
        if not isinstance(declared, list):
            problems.append("the committed build info declares no apt packages")
        else:
            for package in TRACKED_APT_PACKAGES:
                if package not in declared:
                    problems.append(f"the committed build info does not declare {package}")
        # The versions actually installed in the CI-built image are recorded
        # (TZ 22.4 "package versions"). They are not pinned - apt resolves them
        # at build time - but a *recorded* version must exist and must be a
        # real version string, so "unknown" can never be published as fact.
        observed = committed.get("apt_packages_observed")
        if not isinstance(observed, dict):
            problems.append("the committed build info records no observed apt package versions")
        else:
            for package in TRACKED_APT_PACKAGES:
                version = observed.get(package)
                if not version:
                    problems.append(
                        f"the committed build info records no version for the {package} package"
                    )
                elif version == "unknown":
                    problems.append(
                        f"the recorded version for the {package} package is 'unknown', not a fact"
                    )

    return {
        "status": "PASS" if not problems else "FAIL",
        "problems": problems,
        "warnings": warnings,
        "base_image": parsed["base_image_arg"],
        "base_image_digest": parsed["base_image_digest"],
        "pinned": pinned,
        "build_info": committed,
    }


# --------------------------------------------------------------------------- #
# resolve (Docker required)
# --------------------------------------------------------------------------- #
def _docker(*args: str, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
    )


def resolve_digest(base_name: str) -> tuple[str | None, str | None]:
    """The current digest of ``base_name`` (``None`` when it cannot be read)."""
    if shutil.which("docker") is None:
        return None, "docker is not available on this host"
    pull = _docker("pull", base_name)
    if pull.returncode != 0:
        return None, (pull.stderr or pull.stdout).strip()[-400:]
    inspect = _docker(
        "image", "inspect", "--format", "{{index .RepoDigests 0}}", base_name
    )
    if inspect.returncode != 0:
        return None, (inspect.stderr or inspect.stdout).strip()[-400:]
    repo_digest = inspect.stdout.strip()
    _, _, digest = repo_digest.partition("@")
    return (digest or None), None


def read_image_build_info(image: str = "twinledger:eval") -> tuple[dict[str, Any] | None, str | None]:
    """Read the build-info record from *inside* the built image."""
    if shutil.which("docker") is None:
        return None, "docker is not available on this host"
    proc = _docker(
        "run", "--rm", "--network=none", "--read-only", "--entrypoint", "cat",
        image, IMAGE_BUILD_INFO,
    )
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()[-400:]
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"the image build info is not valid JSON: {exc}"


def resolve(report_status: bool = False) -> dict[str, Any]:
    """Resolve the live tag digest and compare it with the pinned digest."""
    parsed = parse_dockerfile()
    if "error" in parsed:
        return {"status": "FAIL", "problems": [parsed["error"]]}
    pinned = parsed["base_image_digest"]
    name = parsed["base_image_name"]
    current, error = resolve_digest(name)
    result: dict[str, Any] = {
        "pinned_digest": pinned,
        "current_tag_digest": current,
        "base_image": name,
        "error": error,
        "drift": None,
        "status": "PASS",
        "problems": [],
    }
    if current is None:
        result["status"] = "UNRESOLVED"
        result["problems"].append(error or "the tag digest could not be resolved")
        return result
    if pinned and current != pinned:
        # Informational only: the pinned digest is what the image uses, and a
        # moved upstream tag must not silently change the release.
        result["drift"] = "the upstream tag moved; the pinned digest is still used"
    image_info, image_error = read_image_build_info()
    result["image_build_info"] = image_info
    if image_error:
        result["image_build_info_error"] = image_error
    return result


# --------------------------------------------------------------------------- #
# CI status reporting
# --------------------------------------------------------------------------- #
def report_commit_status(result: dict[str, Any]) -> bool:
    """Post the resolved digest as a commit status (readable via the API)."""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")
    if not (token and repo and sha):
        return False
    current = result.get("current_tag_digest") or "unresolved"
    pinned = result.get("pinned_digest") or "unpinned"
    drift = "DRIFT" if result.get("drift") else "MATCH"
    description = f"base {drift} pinned={pinned[:19]}… tag={current[:19]}…"
    description = description[:140]
    state = "success" if result.get("status") in {"PASS", "UNRESOLVED"} else "failure"
    payload = json.dumps(
        {"state": state, "description": description, "context": "base-image-digest"}
    )
    proc = subprocess.run(
        [
            "curl", "--silent", "--show-error", "--fail",
            "-X", "POST",
            "-H", f"Authorization: Bearer {token}",
            "-H", "Accept: application/vnd.github+json",
            "-H", "X-GitHub-Api-Version: 2022-11-28",
            "-d", payload,
            f"https://api.github.com/repos/{repo}/statuses/{sha}",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return proc.returncode == 0


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def publish(image: str = "twinledger:eval") -> dict[str, Any]:
    """Read the built image's provenance record and publish it for review.

    The record is emitted as a GitHub Actions annotation (readable through the
    check-run annotations API) and compared with the committed
    ``configs/docker_build_info.json`` so that drift is visible in CI.
    """
    info, error = read_image_build_info(image)
    result: dict[str, Any] = {
        "image": image,
        "image_build_info": info,
        "error": error,
        "problems": [],
        "warnings": [],
        "status": "PASS",
    }
    if info is None:
        result["status"] = "UNAVAILABLE"
        result["problems"].append(error or "the image build info could not be read")
    else:
        committed: dict[str, Any] | None = None
        if BUILD_INFO_PATH.is_file():
            try:
                committed = json.loads(BUILD_INFO_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                result["problems"].append(f"{BUILD_INFO_PATH.name} is not valid JSON: {exc}")
        if committed is not None:
            # The *pinned* facts: the base image, its digest and the Python
            # patch version are fixed by the digest, so a difference means the
            # image is no longer the released one -> a hard problem.
            for key in ("base_image", "base_image_digest", "python_version"):
                if committed.get(key) != info.get(key):
                    result["problems"].append(
                        f"{key}: committed {committed.get(key)!r} != image {info.get(key)!r}"
                    )
            # The Debian package versions are *resolved by apt at build time*
            # (L11) and are therefore not pinned. The committed record holds the
            # version observed in the CI-built image; a difference is reported
            # as drift, not as a failure.
            committed_packages = committed.get("apt_packages_observed") or {}
            image_packages = info.get("apt_packages") or {}
            for package in TRACKED_APT_PACKAGES:
                expected = committed_packages.get(package)
                actual = image_packages.get(package)
                if expected and expected != actual:
                    result["warnings"].append(
                        f"apt package {package}: recorded {expected!r} != image {actual!r} "
                        "(resolved by apt at build time; not pinned - see limitation L11)"
                    )
            result["image_apt_package_versions"] = image_packages
        if result["problems"]:
            result["status"] = "DRIFT"
    if os.environ.get("GITHUB_ACTIONS") == "true":
        payload = json.dumps(info if info is not None else {"error": error}, sort_keys=True)
        print(f"::notice title=image-build-info::{payload}")
        for warning in result["warnings"]:
            print(f"::warning title=image-build-info-drift::{warning}")
        for problem in result["problems"]:
            print(f"::error title=image-build-info-drift::{problem}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger base-image pinning tools")
    sub = parser.add_subparsers(dest="command", required=True)

    emit = sub.add_parser("emit", help="write the image provenance record (inside the image)")
    emit.add_argument("--base-image", default="", help="the ARG BASE_IMAGE value")
    emit.add_argument("--out", default="", help="write the JSON to this path")

    verify_parser = sub.add_parser("verify", help="static check of the pinning contract")
    verify_parser.add_argument(
        "--allow-unpinned",
        action="store_true",
        help="report an unpinned base image as a warning instead of a failure",
    )
    verify_parser.add_argument("--json", action="store_true")
    verify_parser.add_argument(
        "--require-build-info",
        action="store_true",
        help="fail when configs/docker_build_info.json is missing",
    )

    resolve_parser = sub.add_parser("resolve", help="resolve the live tag digest (needs Docker)")
    resolve_parser.add_argument("--report-status", action="store_true")
    resolve_parser.add_argument("--json", action="store_true")

    publish_parser = sub.add_parser("publish", help="publish the built image's provenance record")
    publish_parser.add_argument("--image", default="twinledger:eval")
    publish_parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "emit":
        info = emit_build_info(args.base_image)
        text = json.dumps(info, indent=2, sort_keys=True) + "\n"
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0

    if args.command == "verify":
        result = verify(
            require_pinned=not args.allow_unpinned,
            require_build_info=args.require_build_info,
        )
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"base-image: {result['status']} ({result.get('base_image')})")
            for problem in result["problems"]:
                print(f"  - {problem}")
            for warning in result.get("warnings", []):
                print(f"  ! {warning}")
        return 0 if result["status"] == "PASS" else 1

    # NOTE: this branch used to sit *inside* the ``verify`` branch, after its
    # ``return`` -- unreachable dead code.  ``publish`` therefore fell through
    # to ``resolve()`` and died with
    # ``AttributeError: 'Namespace' object has no attribute 'report_status'``
    # (exit code 1), which the workflow masked with ``|| true``: the CI step
    # named "Publish the image build provenance" never published anything.
    # See docs/QUALITY_AUDIT/BUG_REGISTRY.md (BUG-TL-0016).
    if args.command == "publish":
        result = publish(args.image)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"image-build-info: {result['status']}")
            for warning in result.get("warnings", []):
                print(f"  ! {warning}")
            for problem in result["problems"]:
                print(f"  - {problem}")
        return 0 if result["status"] in {"PASS", "UNAVAILABLE"} else 1

    result = resolve()
    if args.report_status:
        report_commit_status(result)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        payload = json.dumps(
            {
                "pinned_digest": result.get("pinned_digest"),
                "current_tag_digest": result.get("current_tag_digest"),
                "drift": result.get("drift"),
            },
            sort_keys=True,
        )
        print(f"::notice title=base-image-digest::{payload}")
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"base-image-digest: {result['status']}")
        print(f"  pinned : {result['pinned_digest']}")
        print(f"  tag now: {result['current_tag_digest']}")
        if result.get("drift"):
            print(f"  note   : {result['drift']}")
        for problem in result["problems"]:
            print(f"  - {problem}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
