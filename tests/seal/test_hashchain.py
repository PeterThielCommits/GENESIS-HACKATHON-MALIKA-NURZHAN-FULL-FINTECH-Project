"""Tests for deterministic trajectory hash chain (Phase 9, Task 9.5 — REQ-SEAL-021)."""

from __future__ import annotations

import copy
import unittest

from harness.trajectory import TrajectoryRecorder
from seal.hashchain import (
    HashChainBuilder,
    compute_event_hash,
    compute_initial_hash,
    verify_hash_chain,
)

SAMPLE_COMMITMENT = "a" * 64


class TestTrajectoryHashChain(unittest.TestCase):
    def test_seal_and_harness_builders_produce_byte_identical_chains(self) -> None:
        seal_builder = HashChainBuilder(
            truth_commitment=SAMPLE_COMMITMENT,
            episode_id="ep_hash_001",
        )
        harness_rec = TrajectoryRecorder(
            episode_id="ep_hash_001",
            truth_commitment=SAMPLE_COMMITMENT,
        )
        self.assertEqual(seal_builder.initial_hash, harness_rec.initial_hash)

        turns = [
            ("reset", {"event": "reset"}, {"mode": "CLOSED_EVAL", "remaining_steps": 100}, 0),
            ("tool_call", {"tool": "list_records", "page": 1}, {"ok": True, "rows": [1, 2]}, 1),
            ("submit", {"tool": "submit", "findings": []}, {"ok": True, "accepted": True}, 1),
            ("terminate", {"lifecycle": "terminate"}, {"terminated": True, "steps_used": 1}, 1),
        ]
        for etype, act, resp, lstep in turns:
            ev_s = seal_builder.append(
                event_type=etype,
                action_payload=act,
                response_payload=resp,
                logical_step=lstep,
            )
            entry_h = harness_rec.record_event(
                event_type=etype,
                action_payload=act,
                response_payload=resp,
                logical_step=lstep,
                elapsed_ns=123456,  # diagnostic timing must NEVER alter TrajectoryEvent or head!
            )
            self.assertEqual(ev_s.to_dict(), entry_h.trajectory_event.to_dict())
            self.assertEqual(seal_builder.head, entry_h.chain_head_after)

        res = verify_hash_chain(
            SAMPLE_COMMITMENT,
            "ep_hash_001",
            [e.to_dict() for e in seal_builder.events],
            expected_head=harness_rec.head,
        )
        self.assertTrue(res.valid)
        self.assertEqual(res.event_count, 4)

    def test_every_mutation_changes_head_and_fails_verification(self) -> None:
        builder = HashChainBuilder(truth_commitment=SAMPLE_COMMITMENT, episode_id="ep_mut_01")
        builder.append(event_type="reset", action_payload={"r": 0}, response_payload={"ok": True}, logical_step=0)
        builder.append(event_type="tool_call", action_payload={"t": 1}, response_payload={"ok": True}, logical_step=1)
        builder.append(event_type="submit", action_payload={"s": []}, response_payload={"ok": True}, logical_step=1)

        orig_events = [e.to_dict() for e in builder.events]
        orig_head = builder.head

        # 1. Flip one hex char in action_digest of event 1
        m_act = copy.deepcopy(orig_events)
        d0 = m_act[1]["action_digest"]
        m_act[1]["action_digest"] = ("0" if d0[0] != "0" else "1") + d0[1:]
        r1 = verify_hash_chain(SAMPLE_COMMITMENT, "ep_mut_01", m_act, expected_head=orig_head)
        self.assertFalse(r1.valid)

        # 2. Flip one hex char in response_digest of event 0 (breaks event 1 previous_hash linkage!)
        m_resp = copy.deepcopy(orig_events)
        r0 = m_resp[0]["response_digest"]
        m_resp[0]["response_digest"] = ("0" if r0[0] != "0" else "1") + r0[1:]
        r2 = verify_hash_chain(SAMPLE_COMMITMENT, "ep_mut_01", m_resp, expected_head=orig_head)
        self.assertFalse(r2.valid)

        # 3. Truncate last event (prefix chain has different head)
        r3 = verify_hash_chain(SAMPLE_COMMITMENT, "ep_mut_01", orig_events[:-1], expected_head=orig_head)
        self.assertFalse(r3.valid)

        # 4. Swap events 1 and 2
        m_swap = [orig_events[0], orig_events[2], orig_events[1]]
        r4 = verify_hash_chain(SAMPLE_COMMITMENT, "ep_mut_01", m_swap, expected_head=orig_head)
        self.assertFalse(r4.valid)

        # 5. Different episode_id or different truth_commitment changes h_0
        r5 = verify_hash_chain(SAMPLE_COMMITMENT, "ep_mut_02", orig_events, expected_head=orig_head)
        self.assertFalse(r5.valid)
        r6 = verify_hash_chain("b" * 64, "ep_mut_01", orig_events, expected_head=orig_head)
        self.assertFalse(r6.valid)

        # 6. Regressing logical_step rejected
        with self.assertRaises(ValueError):
            builder.append(event_type="tool_call", action_payload={"t": 2}, response_payload={"ok": True}, logical_step=0)

    def test_wall_clock_fields_explicitly_rejected(self) -> None:
        h0 = compute_initial_hash(SAMPLE_COMMITMENT, "ep_wc")
        bad_ev = {
            "schema_version": "1.0.0",
            "event_index": 0,
            "event_type": "reset",
            "action_digest": "0" * 64,
            "response_digest": "1" * 64,
            "protocol_version": "1.0",
            "logical_step": 0,
            "previous_hash": h0,
            "x_twinledger_wall_clock_timestamp": "2026-11-21T00:00:00Z",
        }
        with self.assertRaises(ValueError):
            compute_event_hash(h0, bad_ev)
        res = verify_hash_chain(SAMPLE_COMMITMENT, "ep_wc", [bad_ev])
        self.assertFalse(res.valid)


if __name__ == "__main__":
    unittest.main()
