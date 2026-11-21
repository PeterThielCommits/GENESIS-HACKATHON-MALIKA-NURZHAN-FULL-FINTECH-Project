"""Isolated external Policy subprocess manager (Phase 9, Task 9.1).

Runs external policies inside an empty ``IsolatedPolicyWorkspace`` (``0o555``
temporary directory in ``/tmp`` containing zero episode/public/sealed files)
communicating strictly via stdin/stdout JSONL pipes with sanitized environment
variables and closed extra file descriptors (REQ-ARC-003, REQ-SEAL-002,
REQ-SEAL-004, REQ-SEAL-005).

Imports ONLY ``contracts/``, ``harness.*``, and Python 3.11 stdlib.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Sequence

from harness.protocol import (
    MAX_JSONL_LINE_BYTES,
    assert_policy_outbound_clean,
    format_policy_reset_frame,
    format_policy_response_frame,
    format_policy_terminate_frame,
    read_bounded_line,
    write_jsonl_line,
)
from harness.sandbox import (
    IsolatedPolicyWorkspace,
    build_sanitized_env,
    make_posix_preexec,
)


class PolicySubprocess:
    """Lifecycle wrapper around the isolated ``P1 POLICY`` subprocess."""

    def __init__(
        self,
        argv: Sequence[str],
        *,
        include_repo_pythonpath: bool = True,
        extra_pythonpath: Path | None = None,
        forbidden_tokens: Sequence[str] = (),
    ) -> None:
        if not argv or not all(isinstance(a, str) and a for a in argv):
            raise ValueError("policy argv must be a non-empty sequence of non-empty strings")
        self._argv = tuple(argv)
        self._include_repo_pythonpath = include_repo_pythonpath
        self._extra_pythonpath = extra_pythonpath
        self._forbidden_tokens = tuple(forbidden_tokens)
        self._workspace: IsolatedPolicyWorkspace | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._started_ns: int | None = None
        self._exited_ns: int | None = None

    @property
    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def started_ns(self) -> int | None:
        return self._started_ns

    @property
    def exited_ns(self) -> int | None:
        return self._exited_ns

    @property
    def cwd(self) -> Path | None:
        return self._workspace.cwd if self._workspace is not None else None

    def start(self) -> None:
        """Create empty policy scratch cwd and spawn external policy process."""
        if self._proc is not None:
            raise RuntimeError("PolicySubprocess already started")

        ws = IsolatedPolicyWorkspace()
        ws.__enter__()
        self._workspace = ws

        try:
            self._started_ns = time.monotonic_ns()
            self._proc = subprocess.Popen(
                list(self._argv),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(ws.cwd),
                env=build_sanitized_env(
                    role="POLICY",
                    include_repo_pythonpath=self._include_repo_pythonpath,
                    extra_pythonpath=self._extra_pythonpath,
                ),
                close_fds=True,
                shell=False,
                preexec_fn=make_posix_preexec(),
            )
        except Exception:
            self.close()
            raise

    def send_reset(self, observation: dict[str, Any]) -> None:
        """Send initial public observation frame to Policy stdin after leak check."""
        if self._proc is None or not self.is_alive:
            raise RuntimeError("policy subprocess is not running")
        frame = format_policy_reset_frame(observation)
        assert_policy_outbound_clean(frame, extra_forbidden_tokens=self._forbidden_tokens)
        write_jsonl_line(self._proc, frame)

    def send_response(self, tool_response: dict[str, Any]) -> None:
        """Send validated tool response frame to Policy stdin after leak check."""
        if self._proc is None or not self.is_alive:
            return
        frame = format_policy_response_frame(tool_response)
        assert_policy_outbound_clean(frame, extra_forbidden_tokens=self._forbidden_tokens)
        try:
            write_jsonl_line(self._proc, frame)
        except BrokenPipeError:
            pass

    def send_terminate(self, reason: str) -> None:
        """Best-effort send termination notice to Policy stdin."""
        if self._proc is None or not self.is_alive:
            return
        frame = format_policy_terminate_frame(reason)
        try:
            write_jsonl_line(self._proc, frame)
        except (BrokenPipeError, OSError):
            pass

    def read_request_line(
        self,
        *,
        deadline_monotonic: float,
        max_bytes: int = MAX_JSONL_LINE_BYTES,
    ) -> tuple[str | None, str]:
        """Read next JSONL ``tool_request`` line from Policy stdout."""
        if self._proc is None:
            return None, "eof"
        return read_bounded_line(
            self._proc,
            deadline_monotonic=deadline_monotonic,
            max_bytes=max_bytes,
        )

    def close(self) -> int:
        """Close pipes, terminate ``policy`` subprocess, clean scratch cwd, return ``exited_ns``."""
        proc = self._proc
        if proc is not None:
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2.0)
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            self._proc = None

        if self._workspace is not None:
            self._workspace.cleanup()
            self._workspace = None

        if self._exited_ns is None:
            self._exited_ns = time.monotonic_ns()
        return self._exited_ns


__all__ = ["PolicySubprocess"]
