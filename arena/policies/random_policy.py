"""Baseline Policy 1: Deterministic fixed-seed random exploration policy.

Strictly public-only: interacts exclusively via the 5 canonical actions
(``list_records``, ``get_record``, ``get_document``, ``calculator``, ``submit``)
inside an isolated worker process.
"""

from __future__ import annotations

import random
from typing import Any

from arena.policies.base import BasePolicy


class RandomExplorationPolicy(BasePolicy):
    """Explores public tables/records/documents randomly with a fixed seed."""

    name = "random"

    def __init__(self, seed: int = 0, max_explore_steps: int = 12) -> None:
        self._seed = int(seed)
        self._max_explore_steps = max(1, min(90, int(max_explore_steps)))
        self._rng = random.Random(self._seed)
        self._step_count = 0
        self._seen_records: list[tuple[str, str]] = []
        self._seen_docs: list[str] = []
        self._base_currency = "KZT"
        self._tables = ["ledger", "invoices", "payments", "fx"]

    def reset(self, observation: dict[str, Any]) -> None:
        self._rng = random.Random(self._seed)
        self._step_count = 0
        self._seen_records = []
        self._seen_docs = []
        manifest = observation.get("manifest", {})
        if isinstance(manifest, dict):
            self._base_currency = str(manifest.get("base_currency", "KZT"))

    def _harvest_ids(self, observation: dict[str, Any]) -> None:
        result = observation.get("result")
        if not isinstance(result, dict):
            return
        records = result.get("records")
        if not isinstance(records, list):
            return
        for row in records:
            if not isinstance(row, dict):
                continue
            if "je_id" in row:
                self._seen_records.append(("ledger", str(row["je_id"])))
            elif "doc_id" in row:
                self._seen_records.append(("invoices", str(row["doc_id"])))
                self._seen_docs.append(str(row["doc_id"]))
            elif "pay_id" in row:
                self._seen_records.append(("payments", str(row["pay_id"])))
            elif "fx_id" in row:
                self._seen_records.append(("fx", str(row["fx_id"])))

    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        self._harvest_ids(observation)
        remaining = int(observation.get("remaining_steps", 1))
        if self._step_count >= self._max_explore_steps or remaining <= 1:
            return {"name": "submit", "args": {"findings": {"findings": []}}}

        self._step_count += 1
        choice = self._rng.randrange(4)
        if choice == 0 or not self._seen_records:
            tbl = self._rng.choice(self._tables)
            return {
                "name": "list_records",
                "args": {"table": tbl, "cursor": None, "limit": 25},
            }
        if choice == 1:
            tbl, rec_id = self._rng.choice(self._seen_records)
            return {"name": "get_record", "args": {"table": tbl, "id": rec_id}}
        if choice == 2 and self._seen_docs:
            doc_id = self._rng.choice(self._seen_docs)
            return {"name": "get_document", "args": {"doc_id": doc_id}}
        a = self._rng.randint(10, 999)
        b = self._rng.randint(10, 999)
        return {"name": "calculator", "args": {"expression": f"{a}+{b}"}}


__all__ = ["RandomExplorationPolicy"]
