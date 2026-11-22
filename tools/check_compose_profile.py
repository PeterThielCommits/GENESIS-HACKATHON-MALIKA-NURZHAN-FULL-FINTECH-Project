#!/usr/bin/env python3
"""Static guard for the hardened container profile (``docker-compose.yml``).

The Compose file is the second, judge-facing way of running the benchmark
(TZ §16.2, §22.4, §22.5): it describes the *offline* verification container
and the two sandbox containers that policy and environment processes run in.
Nothing in CI executes it, so a silent regression -- a service that regains
network access, a ``read_only: false``, a bind mount of the sealed tree --
would reach the jury unnoticed.

This tool parses the Compose file with a small YAML-subset reader (the
standard library only: the hardened image has no third-party packages) and
checks every service against the hardening contract:

* ``network_mode: none``            -- no network in any container (TZ 22.4)
* ``read_only: true``               -- the image tree is read-only (TZ 16.2)
* ``cap_drop: [ALL]``               -- no Linux capabilities
* ``security_opt: no-new-privileges:true``
* ``user: 10001:10001``             -- never root (TZ 22.4)
* ``cpus <= 2`` and ``mem_limit <= 4g``   (TZ 22.5 resource limits)
* ``pids_limit`` and an ``fsize`` ulimit  (TZ 16.2 "resource limits ... where
  supported": processes and file size)
* no bind mounts at all, and no tmpfs that could expose ``sealed/`` truth

Exit codes: 0 = the profile satisfies the contract, 4 = it does not.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"

#: The resource ceilings from TZ 22.5 (CPU: 2 cores, RAM: 4 GB).
MAX_CPUS = 2.0
MAX_MEMORY_MB = 4096

#: The container uid/gid from the Dockerfile.
EXPECTED_USER = "10001:10001"

#: The writable paths the verification container needs (tmpfs in CI).
REQUIRED_VERIFY_TMPFS = (
    "/app/artifacts/reports/latest",
    "/app/artifacts/reports/doc_claims",
    "/app/artifacts/trajectories",
)

_SIZE_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([kmg]?)b?\s*$", re.IGNORECASE)
_SIZE_FACTORS = {"": 1 / 1024 / 1024, "k": 1 / 1024, "m": 1.0, "g": 1024.0}


def parse_size_mb(value: Any) -> float | None:
    """Parse a Docker size string (``4g``, ``512m``, ``1048576``) into MiB."""
    if isinstance(value, (int, float)):
        return float(value) / (1024 * 1024)
    if not isinstance(value, str):
        return None
    match = _SIZE_RE.match(value)
    if not match:
        return None
    number, unit = match.groups()
    return float(number) * _SIZE_FACTORS[unit.lower()]


# --------------------------------------------------------------------------- #
# a very small YAML-subset reader
# --------------------------------------------------------------------------- #
def _scalar(text: str) -> Any:
    value = text.strip()
    if not value:
        return ""
    if value[0] in "\"'":
        quote = value[0]
        end = value.find(quote, 1)
        if end > 0:
            return value[1:end]
    lowered = value.lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if lowered in {"null", "~"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _strip_comment(line: str) -> str:
    out: list[str] = []
    quote: str | None = None
    for index, char in enumerate(line):
        if quote:
            out.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            out.append(char)
            continue
        if char == "#" and (index == 0 or line[index - 1] in " \t"):
            break
        out.append(char)
    return "".join(out).rstrip()


def _split_key_value(text: str) -> tuple[str, str] | None:
    """Split ``key: value`` the way YAML does.

    A colon only introduces a mapping when it is followed by a space or ends
    the line; ``/tmp:rw,noexec`` is therefore a plain scalar, not a mapping.
    """
    for index, char in enumerate(text):
        if char != ":":
            continue
        if index + 1 == len(text) or text[index + 1] in " \t":
            return text[:index].strip(), text[index + 1 :].strip()
    return None


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the block-mapping / block-sequence subset the Compose file uses.

    The reader is deliberately small: it understands nested block mappings,
    block sequences, scalars and ``- key: value`` sequence items, which is
    everything ``docker-compose.yml`` needs. Anything else raises
    ``ValueError`` instead of guessing.
    """
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line.strip():
            continue
        lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ValueError(f"unparsed content at line {index + 1}: {lines[index][1]!r}")
    return value if isinstance(value, dict) else {}


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    """Parse one block at ``indent`` starting at ``lines[index]``."""
    if lines[index][1].startswith("- "):
        return _parse_sequence(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_sequence(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent < indent:
            break
        if line_indent > indent or not content.startswith("- "):
            raise ValueError(f"unexpected sequence item: {content!r}")
        body = content[2:].strip()
        index += 1
        pair = None if body.startswith(("'", '"')) else _split_key_value(body)
        if pair is not None:
            key, value = pair
            entry: dict[str, Any] = {}
            if value.strip():
                entry[key] = _scalar(value)
            else:
                child, index = _parse_block(lines, index, line_indent + 1)
                entry[key] = child
            # A mapping item may continue with deeper keys.
            while index < len(lines) and lines[index][0] > line_indent:
                extra, index = _parse_mapping(lines, index, lines[index][0])
                if isinstance(extra, dict):
                    entry.update(extra)
            items.append(entry)
        else:
            items.append(_scalar(body))
    return items, index


def _parse_mapping(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    mapping: dict[str, Any] = {}
    while index < len(lines):
        line_indent, content = lines[index]
        if line_indent < indent:
            break
        if line_indent > indent:
            raise ValueError(f"unexpected indentation at {content!r}")
        if content.startswith("- "):
            break
        pair = _split_key_value(content)
        if pair is None:
            raise ValueError(f"not a mapping entry: {content!r}")
        key, value = pair
        index += 1
        if value:
            mapping[key] = _scalar(value)
            continue
        # An empty value introduces a nested block (mapping or sequence).
        if index < len(lines) and lines[index][0] > indent:
            child, index = _parse_block(lines, index, lines[index][0])
            mapping[key] = child
        else:
            mapping[key] = {}
    return mapping, index


# --------------------------------------------------------------------------- #
# the contract
# --------------------------------------------------------------------------- #
def check_service(name: str, service: dict[str, Any]) -> list[str]:
    """Return the hardening violations of one Compose service."""
    problems: list[str] = []

    def fail(message: str) -> None:
        problems.append(f"{name}: {message}")

    if service.get("network_mode") != "none":
        fail(f"network_mode must be 'none' (got {service.get('network_mode')!r})")
    if service.get("read_only") is not True:
        fail(f"read_only must be true (got {service.get('read_only')!r})")
    cap_drop = service.get("cap_drop") or []
    if isinstance(cap_drop, str):
        cap_drop = [cap_drop]
    if "ALL" not in cap_drop:
        fail("cap_drop must contain ALL")
    security_opt = service.get("security_opt") or []
    if isinstance(security_opt, str):
        security_opt = [security_opt]
    if not any("no-new-privileges" in str(option) for option in security_opt):
        fail("security_opt must contain no-new-privileges:true")
    if str(service.get("user")) != EXPECTED_USER:
        fail(f"user must be {EXPECTED_USER} (got {service.get('user')!r})")

    cpus = service.get("cpus")
    if not isinstance(cpus, (int, float)) or float(cpus) > MAX_CPUS:
        fail(f"cpus must be <= {MAX_CPUS} (got {cpus!r})")
    memory = parse_size_mb(service.get("mem_limit"))
    if memory is None or memory > MAX_MEMORY_MB:
        fail(f"mem_limit must be <= {MAX_MEMORY_MB} MiB (got {service.get('mem_limit')!r})")

    pids_limit = service.get("pids_limit")
    if not isinstance(pids_limit, int) or pids_limit <= 0:
        fail(f"pids_limit must be a positive integer (got {pids_limit!r})")

    ulimits = service.get("ulimits") or {}
    if not isinstance(ulimits, dict) or "fsize" not in ulimits:
        fail("ulimits must define an fsize limit")

    volumes = service.get("volumes") or []
    if volumes:
        fail(f"no bind mounts are allowed in the offline profile (got {volumes!r})")

    tmpfs = service.get("tmpfs") or []
    if isinstance(tmpfs, str):
        tmpfs = [tmpfs]
    for entry in tmpfs:
        target = str(entry).split(":", 1)[0]
        if "sealed" in target:
            fail(f"a tmpfs must not expose sealed data ({target})")
    return problems


def check_compose(path: Path = COMPOSE_PATH) -> dict[str, Any]:
    """Check every service of the Compose profile."""
    if not path.is_file():
        return {"status": "FAIL", "problems": [f"{path.name} is missing"], "services": []}
    try:
        document = parse_simple_yaml(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return {"status": "FAIL", "problems": [f"{path.name} is not parsable: {exc}"], "services": []}

    services = document.get("services")
    if not isinstance(services, dict) or not services:
        return {"status": "FAIL", "problems": [f"{path.name} defines no services"], "services": []}

    problems: list[str] = []
    names: list[str] = []
    for name, service in services.items():
        if not isinstance(service, dict):
            problems.append(f"{name}: service definition is not a mapping")
            continue
        names.append(name)
        problems.extend(check_service(name, service))

    verify = services.get("verify")
    if isinstance(verify, dict):
        tmpfs = verify.get("tmpfs") or []
        if isinstance(tmpfs, str):
            tmpfs = [tmpfs]
        targets = {str(entry).split(":", 1)[0] for entry in tmpfs}
        for required in REQUIRED_VERIFY_TMPFS:
            if required not in targets:
                problems.append(f"verify: the writable path {required} must be a tmpfs mount")

    return {
        "status": "PASS" if not problems else "FAIL",
        "problems": problems,
        "services": names,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static guard for the hardened Compose profile")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = check_compose()
    if args.json:
        import json

        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"compose profile: {result['status']} ({', '.join(result['services']) or 'no services'})")
        for problem in result["problems"]:
            print(f"  - {problem}")
    return 0 if result["status"] == "PASS" else 4


if __name__ == "__main__":
    sys.exit(main())
