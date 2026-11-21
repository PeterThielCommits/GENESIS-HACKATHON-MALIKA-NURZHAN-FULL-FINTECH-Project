"""Official Genesis FinTech (2026-11-20) judge adapter entrypoint.

Exposes the exact three required entrypoints at repository root:
  - ``generate_episode(seed: int, config: dict, output_dir: str) -> None``
  - ``make_env() -> OfficialJudgeEnv``
  - ``score_episode(episode_dir: str, findings: dict, inspection_steps: int) -> dict``

All private paths, ``seed``, ``config``, ``truth``, ``provenance``, and
``score_episode`` remain strictly on the judge side. Policies run in an
isolated process and receive only public observations from ``make_env()``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from adapter.official_env import OfficialJudgeEnv
from gen.pipeline import build_episode_from_config
from scoring.official_scorer import (
    collect_accessible_ids_from_episode_dir,
    load_truths_from_episode_dir,
    score_official_findings,
)

LOGGER = logging.getLogger("twinledger.judge_adapter")


def generate_episode(seed: int, config: dict[str, Any] | None, output_dir: str) -> None:
    """Generate one deterministic episode into ``output_dir``.

    Writes public accounting files (``public/``) and ``manifest.json``, plus
    sealed ``sealed/truth.json`` and ``sealed/provenance.json``.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    build_episode_from_config(int(seed), dict(config or {}), out_path)


def score_episode(
    episode_dir: str,
    findings: dict[str, Any] | list[dict[str, Any]],
    inspection_steps: int,
) -> dict[str, Any]:
    """Score submitted findings against sealed truth in ``episode_dir``.

    Returns:
      Valid submit:
        ``{"tp": int, "fp": int, "fn": int, "precision": float,
           "recall": float, "f1": float, "return": float}``
      Invalid submit structure:
        ``{"tp": None, "fp": None, "fn": None, "precision": None,
           "recall": None, "f1": None, "return": -1.0}``
    """
    truths = load_truths_from_episode_dir(episode_dir)
    accessible_ids = collect_accessible_ids_from_episode_dir(episode_dir)
    result = score_official_findings(
        findings,
        truths,
        inspection_steps,
        accessible_ids=accessible_ids,
    )
    if not result.valid:
        LOGGER.warning("invalid submit for %s: %s", episode_dir, result.error)
    return result.to_score_dict()


def _train_reward_callback(
    episode_dir: str,
    findings: Any,
    inspection_steps: int,
) -> float:
    scored = score_episode(episode_dir, findings, inspection_steps)
    return float(scored["return"])


def make_env() -> OfficialJudgeEnv:
    """Create a fresh official TwinLedger audit environment instance."""
    return OfficialJudgeEnv(
        episode_generator_fn=generate_episode,
        train_reward_fn=_train_reward_callback,
    )


__all__ = [
    "OfficialJudgeEnv",
    "generate_episode",
    "make_env",
    "score_episode",
]
