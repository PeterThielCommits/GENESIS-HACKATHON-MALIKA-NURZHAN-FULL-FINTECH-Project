"""Post-termination isolated Scorer subprocess invoker (Phase 9, Task 9.3).

Enforces the strict lifecycle invariant of Master TZ v3.0.0 §3, §16.1,
REQ-ARC-005, and REQ-SEAL-003:
  - ``P3 SCORER`` NEVER starts while ``P2 ENV`` or ``P1 POLICY`` is still alive;
  - ``harness/`` NEVER imports ``scoring/`` or ``seal/`` in Python — instead it
    spawns ``python3 -m scoring.scorer_cli`` in a separate OS subprocess after
    episode termination and pipe teardown.

Imports ONLY ``contracts/``, ``harness.*``, and Python 3.11 stdlib.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from contracts.loader import validate_instance
from harness.sandbox import build_sanitized_env


class ScorerPrematureStartError(RuntimeError):
    """Raised when any caller attempts to start the scorer before env/policy exit."""


@dataclass(frozen=True)
class ScorerProcessResult:
    """Structured result from the post-episode ``P3 SCORER`` subprocess."""

    exit_code: int
    started_ns: int
    exited_ns: int
    summary: dict[str, Any]
    receipt: dict[str, Any]
    score_report: dict[str, Any]
    receipt_path: Path
    score_report_path: Path


def run_scorer_subprocess(
    *,
    episode_dir: Path | str,
    submission_path: Path | str,
    trajectory_path: Path | str,
    policy_id: str,
    output_receipt_path: Path | str,
    output_score_path: Path | str,
    env_alive: bool,
    policy_alive: bool,
    env_exited_ns: int | None,
    policy_exited_ns: int | None,
    merkle_leaf_index: int = 0,
    salt_mode: str = "TEST_FIXTURE",
    reveal_salt: bool = False,
    timeout_s: float = 30.0,
) -> ScorerProcessResult:
    """Launch ``scoring.scorer_cli`` strictly after ``env`` and ``policy`` exit."""
    if env_alive:
        raise ScorerPrematureStartError(
            "REQ-ARC-005 / REQ-SEAL-003 violation: env subprocess is still alive"
        )
    if policy_alive:
        raise ScorerPrematureStartError(
            "REQ-SEAL-002 violation: policy subprocess is still alive"
        )
    if env_exited_ns is None or policy_exited_ns is None:
        raise ScorerPrematureStartError(
            "REQ-ARC-005 violation: env_exited_ns and policy_exited_ns must be recorded prior to scoring"
        )

    ep_path = Path(episode_dir).resolve()
    sub_path = Path(submission_path).resolve()
    traj_path = Path(trajectory_path).resolve()
    rec_path = Path(output_receipt_path).resolve()
    sc_path = Path(output_score_path).resolve()

    argv: list[str] = [
        sys.executable,
        "-m",
        "scoring.scorer_cli",
        "score",
        "--episode-dir",
        str(ep_path),
        "--submission",
        str(sub_path),
        "--trajectory",
        str(traj_path),
        "--policy-id",
        policy_id,
        "--output-receipt",
        str(rec_path),
        "--output-score",
        str(sc_path),
        "--merkle-leaf-index",
        str(merkle_leaf_index),
        "--salt-mode",
        salt_mode,
    ]
    if reveal_salt:
        argv.append("--reveal-salt")

    with tempfile.TemporaryDirectory(prefix="tl_scorer_cwd_") as tmp_cwd:
        started_ns = time.monotonic_ns()
        if started_ns < env_exited_ns or started_ns < policy_exited_ns:
            raise ScorerPrematureStartError("monotonic clock ordering violation before scorer launch")

        proc = subprocess.run(
            argv,
            cwd=tmp_cwd,
            env=build_sanitized_env(role="SCORER", include_repo_pythonpath=True),
            capture_output=True,
            text=True,
            close_fds=True,
            shell=False,
            timeout=timeout_s,
        )
        exited_ns = time.monotonic_ns()

    if not rec_path.is_file() or not sc_path.is_file():
        raise RuntimeError(
            f"scorer subprocess failed to write artifacts (exit_code={proc.returncode})"
        )

    summary = json.loads(proc.stdout.strip()) if proc.stdout.strip() else {}
    receipt = json.loads(rec_path.read_text(encoding="utf-8"))
    score_report = json.loads(sc_path.read_text(encoding="utf-8"))

    r_errs = validate_instance("receipt", receipt)
    if r_errs:
        raise RuntimeError(f"scorer emitted invalid receipt: {r_errs[0]}")

    return ScorerProcessResult(
        exit_code=proc.returncode,
        started_ns=started_ns,
        exited_ns=exited_ns,
        summary=summary,
        receipt=receipt,
        score_report=score_report,
        receipt_path=rec_path,
        score_report_path=sc_path,
    )


def seal_receipt_batch_subprocess(
    receipt_paths: Sequence[Path | str],
    *,
    output_summary_path: Path | str | None = None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Build batch Merkle tree over receipts via isolated ``scoring.scorer_cli``."""
    if not receipt_paths:
        raise ValueError("receipt_paths must be non-empty")
    resolved = [str(Path(p).resolve()) for p in receipt_paths]
    argv: list[str] = [
        sys.executable,
        "-m",
        "scoring.scorer_cli",
        "seal-batch",
        "--receipts",
        *resolved,
    ]
    if output_summary_path is not None:
        argv.extend(["--output-summary", str(Path(output_summary_path).resolve())])

    with tempfile.TemporaryDirectory(prefix="tl_merkle_cwd_") as tmp_cwd:
        proc = subprocess.run(
            argv,
            cwd=tmp_cwd,
            env=build_sanitized_env(role="SCORER", include_repo_pythonpath=True),
            capture_output=True,
            text=True,
            close_fds=True,
            shell=False,
            timeout=timeout_s,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"seal-batch subprocess failed (exit_code={proc.returncode})")
    return json.loads(proc.stdout.strip())


def verify_receipt_subprocess(
    *,
    receipt_path: Path | str,
    manifest_path: Path | str | None = None,
    trajectory_path: Path | str | None = None,
    truth_path: Path | str | None = None,
    salt_hex: str | None = None,
    merkle_root: str | None = None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Run ``python3 -m seal.cli verify-receipt`` in an isolated subprocess."""
    argv: list[str] = [
        sys.executable,
        "-m",
        "seal.cli",
        "verify-receipt",
        "--receipt",
        str(Path(receipt_path).resolve()),
    ]
    if manifest_path is not None:
        argv.extend(["--manifest", str(Path(manifest_path).resolve())])
    if trajectory_path is not None:
        argv.extend(["--trajectory", str(Path(trajectory_path).resolve())])
    if truth_path is not None:
        argv.extend(["--truth", str(Path(truth_path).resolve())])
    if salt_hex is not None:
        argv.extend(["--salt", salt_hex])
    if merkle_root is not None:
        argv.extend(["--merkle-root", merkle_root])

    with tempfile.TemporaryDirectory(prefix="tl_verify_rcpt_") as tmp_cwd:
        proc = subprocess.run(
            argv,
            cwd=tmp_cwd,
            env=build_sanitized_env(role="SCORER", include_repo_pythonpath=True),
            capture_output=True,
            text=True,
            close_fds=True,
            shell=False,
            timeout=timeout_s,
        )
    out = json.loads(proc.stdout.strip()) if proc.stdout.strip() else {"valid": False}
    out["exit_code"] = proc.returncode
    return out


__all__ = [
    "ScorerPrematureStartError",
    "ScorerProcessResult",
    "run_scorer_subprocess",
    "seal_receipt_batch_subprocess",
    "verify_receipt_subprocess",
]
