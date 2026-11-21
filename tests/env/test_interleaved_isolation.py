"""Interleaved Multi-Environment State Isolation Tests (Phase 13 — TZ §20.7).

Proves that stepping 3 distinct ``TwinLedgerEnv`` instances concurrently in
round-robin order produces byte-identical observations, cursors, responses, step
counts, and submitted findings to running each episode in complete isolation.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from contracts.canonical import canonical_json
from contracts.version import PROTOCOL_VERSION
from env.environment import EnvConfig, TwinLedgerEnv

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestInterleavedEnvIsolation(unittest.TestCase):
    def _action_script(self, first_inv_id: str) -> list[dict]:
        return [
            {"tool": "list_records", "args": {"table": "invoices", "page_size": 2}},
            {"tool": "get_document", "args": {"id": first_inv_id}},
            {"tool": "list_records", "args": {"table": "payments", "page_size": 3}},
            {"tool": "calc", "args": {"expression": "1250 + 750"}},
            {"tool": "submit", "args": {"findings": []}},
        ]

    def test_round_robin_interleaved_envs_match_isolated_runs_byte_for_byte(self) -> None:
        dev_dir = REPO_ROOT / "episodes" / "dev"
        ep_dirs = [p for p in sorted(dev_dir.iterdir()) if (p / "public").is_dir()][:3]
        self.assertEqual(len(ep_dirs), 3)

        # 1. Isolated baseline runs
        isolated_traces: list[list[str]] = []
        first_ids: list[str] = []
        for idx, ep in enumerate(ep_dirs):
            env = TwinLedgerEnv(EnvConfig(mode="CLOSED_EVAL"))
            obs = env.reset(ep / "public", cursor_seed=100 + idx)
            r0 = env.step(
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "request_id": "peek",
                    "action": {"tool": "list_records", "args": {"table": "invoices", "page_size": 1}},
                }
            )
            fid = f"INV:{r0['result']['records'][0]['doc_id']}"
            first_ids.append(fid)

            # Re-reset cleanly and record full script
            obs = env.reset(ep / "public", cursor_seed=500 + idx)
            trace = [canonical_json(obs)]
            for step_idx, act in enumerate(self._action_script(fid)):
                resp = env.step(
                    {
                        "protocol_version": PROTOCOL_VERSION,
                        "request_id": f"req-{step_idx}",
                        "action": act,
                    }
                )
                trace.append(canonical_json(resp))
            trace.append(f"steps={env.steps_used};term={env.terminated}")
            isolated_traces.append(trace)

        # 2. Interleaved round-robin execution across all 3 live environments simultaneously
        envs = [TwinLedgerEnv(EnvConfig(mode="CLOSED_EVAL")) for _ in ep_dirs]
        interleaved_traces: list[list[str]] = []
        scripts = [self._action_script(fid) for fid in first_ids]
        for idx, (env, ep) in enumerate(zip(envs, ep_dirs)):
            obs = env.reset(ep / "public", cursor_seed=500 + idx)
            interleaved_traces.append([canonical_json(obs)])

        for step_idx in range(len(scripts[0])):
            for idx, env in enumerate(envs):
                resp = env.step(
                    {
                        "protocol_version": PROTOCOL_VERSION,
                        "request_id": f"req-{step_idx}",
                        "action": scripts[idx][step_idx],
                    }
                )
                interleaved_traces[idx].append(canonical_json(resp))

        for idx, env in enumerate(envs):
            interleaved_traces[idx].append(f"steps={env.steps_used};term={env.terminated}")

        self.assertEqual(interleaved_traces, isolated_traces)


if __name__ == "__main__":
    unittest.main()
