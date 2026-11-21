"""Isolated public-only Environment subprocess manager (Phase 9, Task 9.2).

Launches ``python3 -m env.jsonl_server`` inside an ephemeral ``StagedPublicWorkspace``
containing ONLY read-only ``0o444`` public files in ``0o555`` directories and
ZERO ``sealed/``, ``truth.json``, or ``provenance.json`` files (REQ-ARC-004,
REQ-SEAL-001, REQ-SEAL-005).

Imports ONLY ``contracts/``, ``harness.*``, and Python 3.11 stdlib.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from contracts.loader import validate_instance
from harness.protocol import (
    MAX_JSONL_LINE_BYTES,
    ProtocolError,
    read_bounded_line,
    write_jsonl_line,
)
from harness.sandbox import (
    StagedPublicWorkspace,
    build_sanitized_env,
    make_posix_preexec,
    wrap_argv_with_kernel_sandbox,
)


class EnvSubprocess:
    """Lifecycle wrapper around the isolated ``P2 ENV`` JSONL server subprocess."""

    def __init__(
        self,
        source_public_dir: Path | str,
        *,
        env_config_path: Path | str | None = None,
        cursor_seed: str = "episode",
        require_closed_eval: bool = True,
    ) -> None:
        self._source_public_dir = Path(source_public_dir)
        self._env_config_path = Path(env_config_path).resolve() if env_config_path else None
        self._cursor_seed = cursor_seed
        self._require_closed_eval = require_closed_eval
        self._workspace: StagedPublicWorkspace | None = None
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
    def staged_public_dir(self) -> Path | None:
        return self._workspace.public_dir if self._workspace is not None else None

    def start(self, *, deadline_monotonic: float) -> dict[str, Any]:
        """Stage read-only ``public/``, spawn ``env.jsonl_server``, and read ``ready``."""
        if self._proc is not None:
            raise RuntimeError("EnvSubprocess already started")

        ws = StagedPublicWorkspace(self._source_public_dir)
        ws.__enter__()
        self._workspace = ws

        argv: list[str] = [
            sys.executable,
            "-m",
            "env.jsonl_server",
            str(ws.public_dir),
            "--cursor-seed",
            self._cursor_seed,
        ]
        if self._env_config_path is not None:
            argv.extend(["--config", str(self._env_config_path)])

        episode_parent = self._source_public_dir.resolve().parent
        effective_argv, _ = wrap_argv_with_kernel_sandbox(
            argv,
            mask_dirs=[episode_parent],
            chdir=ws.root_dir,
        )

        try:
            self._started_ns = time.monotonic_ns()
            self._proc = subprocess.Popen(
                effective_argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(ws.root_dir),
                env=build_sanitized_env(role="ENV", include_repo_pythonpath=True),
                close_fds=True,
                shell=False,
                preexec_fn=make_posix_preexec(),
            )
            raw_line, status = read_bounded_line(
                self._proc,
                deadline_monotonic=deadline_monotonic,
                max_bytes=MAX_JSONL_LINE_BYTES * 8,
            )
            if status != "ok" or raw_line is None:
                raise ProtocolError(f"env subprocess failed to emit ready frame ({status})")
            ready_obj = json.loads(raw_line)
            if not isinstance(ready_obj, dict) or ready_obj.get("event") != "ready":
                raise ProtocolError("env subprocess emitted malformed ready frame")
            obs = ready_obj.get("observation")
            if not isinstance(obs, dict):
                raise ProtocolError("env ready observation must be a JSON object")
            if self._require_closed_eval and obs.get("mode") != "CLOSED_EVAL":
                raise ProtocolError(
                    f"CLOSED_EVAL required, but env reported mode={obs.get('mode')!r} (REQ-ENV-030)"
                )
            return obs
        except Exception:
            self.close()
            raise

    def step_line(
        self,
        raw_request_line: str,
        *,
        deadline_monotonic: float,
    ) -> tuple[str, dict[str, Any]]:
        """Send one JSONL request line and receive ``(canonical_line, response_dict)``."""
        if self._proc is None or not self.is_alive:
            raise ProtocolError("env subprocess is not running")
        write_jsonl_line(self._proc, raw_request_line)
        resp_line, status = read_bounded_line(
            self._proc,
            deadline_monotonic=deadline_monotonic,
            max_bytes=MAX_JSONL_LINE_BYTES * 16,
        )
        if status != "ok" or resp_line is None:
            raise ProtocolError(f"env subprocess failed to respond ({status})")
        try:
            resp_obj = json.loads(resp_line)
        except json.JSONDecodeError as exc:
            raise ProtocolError("env subprocess emitted invalid JSON") from exc
        if not isinstance(resp_obj, dict):
            raise ProtocolError("env response must be a JSON object")
        errs = validate_instance("tool_response", resp_obj)
        if errs:
            raise ProtocolError(f"env response violated tool_response schema: {errs[0]}")
        # Enforce CLOSED_EVAL zero reward disclosure (TZ §14.9)
        if self._require_closed_eval and resp_obj.get("ok") and isinstance(resp_obj.get("result"), dict):
            res_dict = resp_obj["result"]
            if "reward" in res_dict and res_dict["reward"] not in (None, 0):
                raise ProtocolError("CLOSED_EVAL violation: non-zero reward in env response")
        return resp_line, resp_obj

    def close(self) -> int:
        """Close pipes, terminate ``env`` subprocess, remove staged dir, return ``exited_ns``."""
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


__all__ = ["EnvSubprocess"]
