"""Baseline Policy 4: Judge-side Oracle policy (sealed-truth reference).

Lives strictly inside ``judge/`` (never in ``arena/policies/``). Constructs
exact findings from the sealed ``truth.json`` on the judge side and submits
them through the standard ``submit`` action after a configurable number of
benign inspection steps (supporting paired invariance checks P01..P20 with
identical ``inspection_steps`` on original and transformed variants).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_oracle_findings_from_episode_dir(episode_dir: Path | str) -> dict[str, Any]:
    """Read sealed truth in ``episode_dir`` and construct exact official findings."""
    root = Path(episode_dir)
    candidates = [root / "sealed" / "truth.json", root / "truth.json"]
    raw_truths: list[dict[str, Any]] | None = None
    for path in candidates:
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw_truths = list(loaded.get("findings", loaded.get("issues", loaded.get("truth", []))))
            elif isinstance(loaded, list):
                raw_truths = loaded
            break
    if raw_truths is None:
        raise FileNotFoundError(f"truth.json not found in {root}")

    findings: list[dict[str, Any]] = []
    for row in raw_truths:
        ev_sets = row.get("evidence_sets")
        if ev_sets and isinstance(ev_sets, list) and ev_sets[0]:
            ev_ids = list(ev_sets[0])
        else:
            ev_ids = list(row.get("evidence_ids", []))
        amt = row["expected_amount_minor"] if "expected_amount_minor" in row else row["amount_minor"]
        findings.append(
            {
                "type": str(row["type"]),
                "affected_ids": list(row["affected_ids"]),
                "claimed_amount_minor": int(amt),
                "currency": str(row["currency"]),
                "evidence_ids": ev_ids[:10],
                "explanation": f"Oracle reference finding for {row.get('issue_id', row.get('truth_id', 'issue'))}.",
            }
        )
    return {"findings": findings}


class JudgeOraclePolicy:
    """Judge-side oracle policy executing ``inspection_steps`` reads then ``submit``."""

    name = "oracle"

    def __init__(self, episode_dir: Path | str, inspection_steps: int = 4) -> None:
        self._episode_dir = str(episode_dir)
        self._target_inspection_steps = max(0, min(99, int(inspection_steps)))
        self._findings_payload = build_oracle_findings_from_episode_dir(episode_dir)
        self._steps_done = 0
        self._tables = ("ledger", "invoices", "payments", "fx")

    def reset(self, observation: dict[str, Any]) -> None:
        _ = observation
        self._steps_done = 0

    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        _ = observation
        if self._steps_done < self._target_inspection_steps:
            tbl = self._tables[self._steps_done % len(self._tables)]
            self._steps_done += 1
            return {
                "name": "list_records",
                "args": {"table": tbl, "cursor": None, "limit": 5},
            }
        return {
            "name": "submit",
            "args": {"findings": self._findings_payload},
        }


__all__ = ["JudgeOraclePolicy", "build_oracle_findings_from_episode_dir"]
