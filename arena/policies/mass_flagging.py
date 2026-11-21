"""Baseline Policy 3: Mass-flagging adversary policy.

Demonstrates reward-shaping resistance against shotgun/mass-flagging attacks:
reads the first page of public ledger entries and flags the first 7 records
with all 4 supported anomaly types (28 structurally valid findings <= 30),
yielding a strongly negative return under the official scorer.
"""

from __future__ import annotations

from typing import Any

from arena.policies.base import BasePolicy

ALL_TYPES: tuple[str, ...] = (
    "DUPLICATE_PAYMENT",
    "PARTIAL_PAYMENT_ALLOCATION",
    "FX_RATE_MISMATCH",
    "PERIOD_CUTOFF",
)


class MassFlaggingPolicy(BasePolicy):
    """Flags multiple records with every anomaly type up to the 30-finding cap."""

    name = "mass_flagging"

    def __init__(self, seed: int = 0) -> None:
        self._seed = int(seed)
        self._base_currency = "KZT"
        self._listed = False

    def reset(self, observation: dict[str, Any]) -> None:
        manifest = observation.get("manifest", {})
        self._base_currency = str(manifest.get("base_currency", "KZT")) if isinstance(manifest, dict) else "KZT"
        self._listed = False

    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        if not self._listed:
            self._listed = True
            return {"name": "list_records", "args": {"table": "ledger", "cursor": None, "limit": 10}}

        res = observation.get("result")
        rows = res.get("records", []) if isinstance(res, dict) else []
        findings: list[dict[str, Any]] = []
        for row in rows[:7]:
            if not isinstance(row, dict):
                continue
            raw_id = str(row.get("je_id") or row.get("row_id") or row.get("id") or "")
            if not raw_id:
                continue
            tid = raw_id if ":" in raw_id else f"JE:{raw_id}"
            lines = row.get("lines", [])
            amt = sum(int(ln.get("functional_debit_minor", 0)) for ln in lines if isinstance(ln, dict)) or 1000
            for atype in ALL_TYPES:
                findings.append(
                    {
                        "type": atype,
                        "affected_ids": [tid],
                        "claimed_amount_minor": amt,
                        "currency": self._base_currency,
                        "evidence_ids": [tid],
                        "explanation": f"Mass-flagging heuristic guess for {tid}.",
                    }
                )
                if len(findings) >= 28:
                    break
            if len(findings) >= 28:
                break

        return {"name": "submit", "args": {"findings": {"findings": findings}}}


__all__ = ["MassFlaggingPolicy"]
