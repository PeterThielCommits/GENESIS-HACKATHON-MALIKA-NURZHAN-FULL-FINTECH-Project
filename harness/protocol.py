"""Versioned JSONL IPC protocol framing and leak-safe stream I/O (Phase 9, Task 9.1).

Implements Master TZ v3.0.0 §14, §16.1, REQ-ARC-006, and REQ-SEAL-005:
  - All inter-process messages use versioned JSONL (``protocol_version: "1.0"``).
  - Enforces bounded line sizes (``MAX_JSONL_LINE_BYTES = 65536``) and wall-clock
    read timeouts via ``select.select``.
  - Validates ``tool_request`` and ``tool_response`` frames against frozen
    ``contracts/`` schemas.
  - Scans outbound policy frames to guarantee zero leakage of sealed filenames,
    ``truth_commitment``, salts, or canary tokens.

Imports ONLY ``contracts/`` and Python 3.11 stdlib (obeys ``harness/`` boundary).
"""

from __future__ import annotations

import json
import select
import subprocess
import time
from typing import Any, Sequence

from contracts.canonical import canonical_json
from contracts.loader import validate_instance
from contracts.version import PROTOCOL_VERSION

MAX_JSONL_LINE_BYTES = 65536

DEFAULT_FORBIDDEN_TOKENS: tuple[str, ...] = (
    "truth.json",
    "provenance.json",
    "sealed/",
    "sealed\\",
    "commitment_salt_hex",
    "truth_commitment",
)


class ProtocolError(RuntimeError):
    """Raised on malformed, oversized, or protocol-violating IPC frames."""


class LeakageViolationError(RuntimeError):
    """Raised immediately if a policy-bound message contains a forbidden token."""


def format_policy_reset_frame(observation: dict[str, Any]) -> str:
    """Format initial reset frame sent from Harness to Policy stdin."""
    return canonical_json(
        {
            "protocol_version": PROTOCOL_VERSION,
            "type": "reset",
            "observation": observation,
        }
    )


def format_policy_response_frame(tool_response: dict[str, Any]) -> str:
    """Format step response frame sent from Harness to Policy stdin."""
    errs = validate_instance("tool_response", tool_response)
    if errs:
        raise ProtocolError(f"invalid tool_response frame: {errs[0]}")
    return canonical_json(
        {
            "protocol_version": PROTOCOL_VERSION,
            "type": "response",
            "response": tool_response,
        }
    )


def format_policy_terminate_frame(reason: str) -> str:
    """Format episode-end notification sent from Harness to Policy stdin."""
    return canonical_json(
        {
            "protocol_version": PROTOCOL_VERSION,
            "type": "terminate",
            "reason": reason,
        }
    )


def assert_policy_outbound_clean(
    serialized_frame: str,
    *,
    extra_forbidden_tokens: Sequence[str] = (),
) -> None:
    """Ensure a message sent to Policy contains zero private paths, hashes, or canaries."""
    for tok in (*DEFAULT_FORBIDDEN_TOKENS, *extra_forbidden_tokens):
        if tok and tok in serialized_frame:
            raise LeakageViolationError(
                "blocked outbound policy message containing forbidden private marker"
            )


def validate_tool_request_line(
    raw_line: str,
    *,
    max_bytes: int = MAX_JSONL_LINE_BYTES,
) -> tuple[dict[str, Any] | None, str | None]:
    """Parse and validate a raw policy JSONL line against ``tool_request.schema.json``.

    Returns ``(parsed_dict, None)`` when valid or ``(parsed_dict_or_None, error_reason)``
    when malformed or schema-invalid (note: malformed requests are still forwarded
    or counted against step budget per ``REQ-ENV-002``).
    """
    raw_bytes = raw_line.encode("utf-8", errors="replace")
    if len(raw_bytes) > max_bytes:
        return None, f"request exceeds max_request_bytes ({max_bytes})"
    try:
        obj = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        return None, f"malformed JSON: {exc.msg}"
    if not isinstance(obj, dict):
        return None, "request must be a JSON object"
    errs = validate_instance("tool_request", obj)
    if errs:
        return obj, errs[0]
    return obj, None


def read_bounded_line(
    proc: subprocess.Popen[bytes],
    *,
    deadline_monotonic: float,
    max_bytes: int = MAX_JSONL_LINE_BYTES,
) -> tuple[str | None, str]:
    """Read one LF-terminated UTF-8 line from ``proc.stdout`` within deadline and byte cap.

    Returns ``(line_without_newline, status)`` where ``status`` is one of:
      - ``"ok"``: valid line read;
      - ``"eof"``: stream closed cleanly;
      - ``"timeout"``: wall-clock deadline exceeded;
      - ``"oversized"``: line exceeded ``max_bytes`` without LF.
    """
    stdout = proc.stdout
    if stdout is None:
        return None, "eof"
    fd = stdout.fileno()
    buf = bytearray()

    while True:
        remaining = deadline_monotonic - time.monotonic()
        if remaining <= 0:
            return None, "timeout"
        ready, _, _ = select.select([fd], [], [], min(remaining, 0.25))
        if not ready:
            if time.monotonic() >= deadline_monotonic:
                return None, "timeout"
            if proc.poll() is not None:
                # Drain any remaining buffered bytes once after exit
                chunk = os.read_nonblocking_safe(fd) if hasattr(os, "read_nonblocking_safe") else b""
                if not chunk:
                    try:
                        chunk = os.read(fd, 1)
                    except OSError:
                        chunk = b""
                if not chunk:
                    if buf:
                        return buf.decode("utf-8", errors="replace").rstrip("\r\n"), "ok"
                    return None, "eof"
                if chunk == b"\n":
                    return buf.decode("utf-8", errors="replace").rstrip("\r"), "ok"
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    return None, "oversized"
            continue

        try:
            byte = os.read(fd, 1)
        except OSError:
            byte = b""
        if not byte:
            if buf:
                return buf.decode("utf-8", errors="replace").rstrip("\r\n"), "ok"
            return None, "eof"
        if byte == b"\n":
            return buf.decode("utf-8", errors="replace").rstrip("\r"), "ok"
        buf.extend(byte)
        if len(buf) > max_bytes:
            return None, "oversized"


import os  # noqa: E402


def write_jsonl_line(proc: subprocess.Popen[bytes], line: str) -> None:
    """Write one UTF-8 JSONL line to ``proc.stdin`` and flush."""
    if proc.stdin is None:
        raise ProtocolError("subprocess stdin is closed")
    data = (line.rstrip("\r\n") + "\n").encode("utf-8")
    proc.stdin.write(data)
    proc.stdin.flush()


__all__ = [
    "DEFAULT_FORBIDDEN_TOKENS",
    "MAX_JSONL_LINE_BYTES",
    "LeakageViolationError",
    "ProtocolError",
    "assert_policy_outbound_clean",
    "format_policy_reset_frame",
    "format_policy_response_frame",
    "format_policy_terminate_frame",
    "read_bounded_line",
    "validate_tool_request_line",
    "write_jsonl_line",
]
