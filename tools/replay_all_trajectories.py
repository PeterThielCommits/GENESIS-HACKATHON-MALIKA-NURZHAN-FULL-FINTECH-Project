#!/usr/bin/env python3
"""Replay every published trajectory (Phase 16, task 16.4; TZ §16).

`make replay` (`harness.replay --verify-suite`) proves determinism on five
reference runs. Task 16.4 asks for something stricter: replay **all published
trajectories** and require that every recorded observation, reward and score
comes back byte-identical.

Method
------
Every row of ``artifacts/trajectories/trajectories.jsonl`` carries the episode
id, the seed, the mode and the *complete* action sequence that the baseline
policy took. This tool rebuilds the canonical D01..D20 episodes with the same
master seed in a temporary directory, then re-executes the recorded actions
against a fresh ``make_env()`` and compares:

  * the initial observation,
  * every step's observation, reward and info,
  * the score returned for the recorded final findings,
  * the recorded metrics.

No policy is re-run, so the check is independent of policy code and of the
isolation harness: it is a pure determinism claim about the environment,
generator, and scorer.

Exit codes (TZ §23.3): 0 = all matched, 1 = mismatch, 2 = configuration error.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import judge_adapter
from gen.pipeline import build_episode, official_d20_recipes

TRAJECTORIES = REPO_ROOT / "artifacts" / "trajectories" / "trajectories.jsonl"
# Deliberately outside artifacts/reports/latest/ (the frozen Judge Kit set).
OUTPUT_PATH = REPO_ROOT / "artifacts" / "reports" / "release" / "trajectory_replay.json"

MASTER_SEED = 2026


def _say(message: str) -> None:
    """ASCII-only console output (the offline container runs LC_ALL=C)."""
    text = (
        message.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2192", "->")
        .replace("\u00a7", "S")
    )
    try:
        print(text)
    except UnicodeEncodeError:  # pragma: no cover - last-resort guard
        print(text.encode("ascii", "replace").decode("ascii"))


def load_trajectories(path: Path = TRAJECTORIES) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing - run `make official-eval` first")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError as exc:
                raise ValueError(f"{path}:{lineno}: unparseable JSON: {exc}") from exc
    if not rows:
        raise ValueError(f"{path} contains no trajectories")
    return rows


def replay_all(*, master_seed: int = MASTER_SEED, trajectories: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Rebuild the canonical episodes, replay every recorded run, compare all."""
    rows = trajectories if trajectories is not None else load_trajectories()
    recipes = official_d20_recipes(master_seed=master_seed)
    # The recipe carries the canonical episode id; the evaluation used
    # master_seed + positional index as the per-episode seed.
    def _recipe_id(recipe: Any) -> str:
        spec = getattr(recipe, "twin_spec", None)
        return str(getattr(spec, "episode_id", getattr(recipe, "episode_id", "")))

    seed_by_id = {_recipe_id(rec): master_seed + idx for idx, rec in enumerate(recipes)}

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="twinledger_replay_all_") as tmp:
        built: dict[str, str] = {}
        for recipe in recipes:
            ge = build_episode(recipe, tmp)
            built[_recipe_id(recipe)] = str(ge.episode_dir)

        for row in rows:
            episode_id = str(row["episode_id"])
            problems: list[str] = []

            ep_dir = built.get(episode_id)
            if ep_dir is None:
                results.append(
                    {
                        "episode_id": episode_id,
                        "policy": row.get("policy"),
                        "matched": False,
                        "problems": [f"episode {episode_id} was not generated from master_seed={master_seed}"],
                    }
                )
                continue

            seed = seed_by_id.get(episode_id, master_seed)
            env = judge_adapter.make_env()
            obs, _info = env.reset(
                seed=seed,
                config={"mode": row.get("mode", "closed"), "episode_dir": ep_dir, "team_config": {}},
            )
            if obs != row["initial_observation"]:
                problems.append("initial observation differs")

            for expected_step in row.get("steps", []):
                action = expected_step["action"]
                out = env.step(action)
                if not isinstance(out, tuple) or len(out) != 5:
                    problems.append(f"step {expected_step.get('step')}: step() did not return a 5-tuple")
                    break
                got_obs, got_reward, got_done, got_trunc, got_info = out
                if got_obs != expected_step.get("observation"):
                    problems.append(f"step {expected_step.get('step')}: observation differs")
                if got_reward != expected_step.get("reward"):
                    problems.append(f"step {expected_step.get('step')}: reward {got_reward} != {expected_step.get('reward')}")
                if got_done != expected_step.get("terminated") and "terminated" in expected_step:
                    problems.append(f"step {expected_step.get('step')}: terminated differs")
                if "info" in expected_step and got_info != expected_step["info"]:
                    problems.append(f"step {expected_step.get('step')}: info differs")
                if problems:
                    break  # first divergence is the useful one; keep the report short

            if row.get("final_findings") is not None:
                scored = judge_adapter.score_episode(
                    ep_dir, row["final_findings"], int(row.get("inspection_steps", 0))
                )
                for key, expected in (row.get("metrics") or {}).items():
                    if key in ("duration_s",):
                        continue  # wall-clock is intentionally not deterministic
                    if scored.get(key) != expected:
                        problems.append(f"score.{key}: {scored.get(key)!r} != {expected!r}")
            env.close()

            results.append(
                {
                    "episode_id": episode_id,
                    "policy": row.get("policy"),
                    "steps_replayed": len(row.get("steps", [])),
                    "matched": not problems,
                    "problems": problems[:5],
                }
            )

    matched = sum(1 for r in results if r["matched"])
    report = {
        "schema_version": "1.0.0",
        "report_type": "trajectory_replay",
        "code_version": "twinledger@1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "command": "python3 tools/replay_all_trajectories.py",
        "master_seed": master_seed,
        "status": "PASS" if matched == len(results) and results else "FAIL",
        "runs_replayed": len(results),
        "runs_matched": matched,
        "steps_replayed": sum(r.get("steps_replayed", 0) for r in results),
        "failures": [r for r in results if not r["matched"]][:10],
        "runs": results,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay all published trajectories (TZ 16.4)")
    parser.add_argument("--master-seed", type=int, default=MASTER_SEED)
    parser.add_argument("--trajectories", default=str(TRAJECTORIES))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        rows = load_trajectories(Path(args.trajectories))
    except (FileNotFoundError, ValueError) as exc:
        _say(f"replay-all: CONFIGURATION ERROR: {exc}")
        return 2

    report = replay_all(master_seed=args.master_seed, trajectories=rows)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0 if report["status"] == "PASS" else 1

    if not args.no_write:
        out = Path(args.output)
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            try:
                shown: Any = out.relative_to(REPO_ROOT)
            except ValueError:
                shown = out
            _say(f"report: {shown}")
        except OSError as exc:
            _say(f"replay-all: note: report not written ({exc.__class__.__name__}); verdict is authoritative")

    if report["status"] == "PASS":
        _say(
            f"replay-all: PASS ({report['runs_matched']}/{report['runs_replayed']} runs, "
            f"{report['steps_replayed']} steps byte-identical)"
        )
        return 0

    _say(f"replay-all: FAIL ({report['runs_matched']}/{report['runs_replayed']} runs matched)")
    for failure in report["failures"]:
        _say(f"  {failure['episode_id']} [{failure.get('policy')}]: {'; '.join(failure['problems'])}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
