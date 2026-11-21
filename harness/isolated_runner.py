"""Process-isolated episode execution harness (C20 + Block 5 trajectories).

Runs public baseline policies inside an OS-isolated child subprocess
(``python3 -m arena.policies.worker``) with a minimal sanitized environment
(zero access to ``episode_dir``, ``sealed/``, ``scoring/``, ``verifier/``,
or ``gen/``). Enforces a strict wall-clock episode timeout (default 60s).

Obeys ``harness/`` import boundaries: never imports ``gen``, ``verifier``,
``scoring``, or ``seal`` — callers pass ``env`` and optional ``score_fn`` via
dependency injection.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class EpisodeRunResult:
    """Complete public trajectory + judge-side metrics for one episode run."""

    episode_id: str
    policy_name: str
    seed: int
    mode: str
    terminated: bool
    truncated: bool
    timed_out: bool
    inspection_steps: int
    actions_used: int
    duration_s: float
    initial_observation: dict[str, Any]
    steps: tuple[dict[str, Any], ...]
    final_findings: Any
    metrics: dict[str, Any] | None

    def to_trajectory_record(self) -> dict[str, Any]:
        """Serialize as one JSONL record for ``trajectories.jsonl`` (zero truth leakage in obs)."""
        return {
            "schema_version": "1.0.0",
            "episode_id": self.episode_id,
            "policy": self.policy_name,
            "seed": self.seed,
            "mode": self.mode,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "timed_out": self.timed_out,
            "inspection_steps": self.inspection_steps,
            "actions_used": self.actions_used,
            "duration_s": round(self.duration_s, 6),
            "initial_observation": self.initial_observation,
            "steps": list(self.steps),
            "final_findings": self.final_findings,
            "metrics": self.metrics,
        }


def _sanitized_worker_env() -> dict[str, str]:
    """Build a minimal environment for isolated policy subprocesses."""
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TWINLEDGER_ISOLATED_POLICY": "1",
    }
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    return env


def _read_line_with_timeout(proc: subprocess.Popen[str], timeout_s: float) -> str | None:
    assert proc.stdout is not None
    if timeout_s <= 0:
        return None
    ready, _, _ = select.select([proc.stdout], [], [], timeout_s)
    if not ready:
        return None
    return proc.stdout.readline()


def run_isolated_public_policy(
    env: Any,
    *,
    policy_name: str,
    episode_dir: str,
    seed: int = 0,
    mode: str = "closed",
    time_limit_s: float = 60.0,
    score_fn: Callable[[str, Any, int], dict[str, Any]] | None = None,
) -> EpisodeRunResult:
    """Run a public policy inside a separate isolated subprocess against ``env``."""
    start = time.monotonic()
    obs, _ = env.reset(
        seed=seed,
        config={
            "mode": mode,
            "episode_dir": episode_dir,
            "team_config": {"time_limit_s": time_limit_s},
        },
    )
    episode_id = str(obs.get("manifest", {}).get("episode_id", Path(episode_dir).name))

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "arena.policies.worker",
            "--policy",
            policy_name,
            "--seed",
            str(seed),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(REPO_ROOT),
        env=_sanitized_worker_env(),
    )

    steps_log: list[dict[str, Any]] = []
    terminated = False
    truncated = False
    timed_out = False

    try:
        assert proc.stdin is not None
        msg_type = "reset"
        current_obs = obs

        while not (terminated or truncated):
            remaining_time = time_limit_s - (time.monotonic() - start)
            if remaining_time <= 0:
                timed_out = True
                truncated = True
                break

            payload = json.dumps({"type": msg_type, "observation": current_obs}, separators=(",", ":"))
            proc.stdin.write(payload + "\n")
            proc.stdin.flush()
            msg_type = "step"

            line = _read_line_with_timeout(proc, remaining_time)
            if not line:
                if time.monotonic() - start >= time_limit_s:
                    timed_out = True
                truncated = True
                break

            resp = json.loads(line)
            action = resp["action"]
            next_obs, reward, terminated, truncated, info = env.step(action)
            steps_log.append(
                {
                    "step": len(steps_log) + 1,
                    "action": action,
                    "observation": next_obs,
                    "reward": reward,
                    "terminated": terminated,
                    "truncated": truncated,
                    "info": info,
                }
            )
            current_obs = next_obs
            if next_obs.get("error") and next_obs["error"].get("code") == "TIME_LIMIT":
                timed_out = True

        try:
            proc.stdin.write(json.dumps({"type": "quit"}) + "\n")
            proc.stdin.flush()
            proc.wait(timeout=2.0)
        except Exception:
            proc.kill()
            proc.wait(timeout=2.0)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2.0)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass

    duration_s = time.monotonic() - start
    final_findings = {"findings": []} if timed_out else env.final_findings
    inspection_steps = env.inspection_steps
    metrics = score_fn(episode_dir, final_findings, inspection_steps) if score_fn is not None else None

    return EpisodeRunResult(
        episode_id=episode_id,
        policy_name=policy_name,
        seed=seed,
        mode=mode,
        terminated=terminated,
        truncated=truncated,
        timed_out=timed_out,
        inspection_steps=inspection_steps,
        actions_used=env.actions_used,
        duration_s=duration_s,
        initial_observation=obs,
        steps=tuple(steps_log),
        final_findings=final_findings,
        metrics=metrics,
    )


def run_inprocess_judge_policy(
    env: Any,
    policy: Any,
    *,
    episode_dir: str,
    seed: int = 0,
    mode: str = "closed",
    time_limit_s: float = 60.0,
    score_fn: Callable[[str, Any, int], dict[str, Any]] | None = None,
) -> EpisodeRunResult:
    """Run a judge-side policy (e.g. Oracle) directly on the judge side."""
    start = time.monotonic()
    obs, _ = env.reset(
        seed=seed,
        config={
            "mode": mode,
            "episode_dir": episode_dir,
            "team_config": {"time_limit_s": time_limit_s},
        },
    )
    episode_id = str(obs.get("manifest", {}).get("episode_id", Path(episode_dir).name))
    policy.reset(obs)

    steps_log: list[dict[str, Any]] = []
    terminated = False
    truncated = False
    timed_out = False
    current_obs = obs

    while not (terminated or truncated):
        if time.monotonic() - start >= time_limit_s:
            timed_out = True
            truncated = True
            break
        action = policy.act(current_obs)
        next_obs, reward, terminated, truncated, info = env.step(action)
        steps_log.append(
            {
                "step": len(steps_log) + 1,
                "action": action,
                "observation": next_obs,
                "reward": reward,
                "terminated": terminated,
                "truncated": truncated,
                "info": info,
            }
        )
        current_obs = next_obs
        if next_obs.get("error") and next_obs["error"].get("code") == "TIME_LIMIT":
            timed_out = True

    duration_s = time.monotonic() - start
    final_findings = {"findings": []} if timed_out else env.final_findings
    inspection_steps = env.inspection_steps
    metrics = score_fn(episode_dir, final_findings, inspection_steps) if score_fn is not None else None

    return EpisodeRunResult(
        episode_id=episode_id,
        policy_name=getattr(policy, "name", "oracle"),
        seed=seed,
        mode=mode,
        terminated=terminated,
        truncated=truncated,
        timed_out=timed_out,
        inspection_steps=inspection_steps,
        actions_used=env.actions_used,
        duration_s=duration_s,
        initial_observation=obs,
        steps=tuple(steps_log),
        final_findings=final_findings,
        metrics=metrics,
    )


__all__ = [
    "EpisodeRunResult",
    "run_inprocess_judge_policy",
    "run_isolated_public_policy",
]
