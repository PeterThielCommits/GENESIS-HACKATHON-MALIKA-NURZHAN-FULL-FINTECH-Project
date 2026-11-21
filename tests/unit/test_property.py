"""Stdlib property loops (TZ 20.2 fallback when Hypothesis is absent).

These deterministic loops cover the Phase 1 properties; Hypothesis-based
property tests are added in Phase 13 as optional extras.
"""

import hashlib
import random
import unittest

from contracts.canonical import canonical_json, sha256_hex
from contracts.models import canonical_ids
from seal.hashchain import HashChainBuilder, verify_hash_chain
from seal.merkle import MerkleTree, verify_inclusion_proof


class TestStdlibProperties(unittest.TestCase):
    def test_canonical_stable_under_key_permutation(self):
        rng = random.Random(42)
        base = {"a": 1, "b": [1, 2, 3], "c": {"x": "y", "n": 7}, "d": "text"}
        keys = list(base.keys())
        for _ in range(50):
            rng.shuffle(keys)
            permuted = {k: base[k] for k in keys}
            self.assertEqual(canonical_json(base), canonical_json(permuted))
            self.assertEqual(sha256_hex(base), sha256_hex(permuted))

    def test_canonical_ids_idempotent(self):
        ids = ["JE:b", "JE:a", "PAY:x", "JE:a"]
        once = canonical_ids(ids)
        twice = canonical_ids(list(once))
        self.assertEqual(once, twice)
        self.assertEqual(list(once), sorted(set(ids)))

    def test_money_int_preserved(self):
        # Money stays int through canonical round-trip (REQ-MONEY-001).
        import json

        payload = {"amount_minor": 123456, "currency": "KZT"}
        parsed = json.loads(canonical_json(payload))
        self.assertIsInstance(parsed["amount_minor"], int)
        self.assertEqual(parsed["amount_minor"], 123456)

    def test_merkle_tree_inclusion_property_across_sizes(self):
        # Deterministic property loop across leaf counts 1..25 (REQ-SEAL-022)
        for n in range(1, 26):
            leaves = [hashlib.sha256(f"prop-leaf-{n}-{i}".encode("utf-8")).hexdigest() for i in range(n)]
            tree = MerkleTree.from_leaves(leaves)
            for idx in range(n):
                proof = tree.inclusion_proof(idx)
                self.assertTrue(verify_inclusion_proof(leaves[idx], idx, n, proof, tree.root))

    def test_hashchain_single_event_mutation_always_detected(self):
        # Any mutation to any event payload changes head and fails verification (REQ-SEAL-021)
        rng = random.Random(909)
        commitment = "c" * 64
        for trial in range(20):
            hb = HashChainBuilder(truth_commitment=commitment, episode_id=f"ep-prop-{trial}")
            hb.append(event_type="reset", action_payload={"seed_idx": trial}, response_payload={"ok": True}, logical_step=0)
            k = rng.randint(1, 6)
            for step in range(1, k + 1):
                hb.append(
                    event_type="tool_call",
                    action_payload={"step": step, "v": rng.randint(0, 10000)},
                    response_payload={"ok": True, "rem": 100 - step},
                    logical_step=step,
                )
            events = [e.to_dict() for e in hb.events]
            head = hb.head
            self.assertTrue(verify_hash_chain(commitment, f"ep-prop-{trial}", events, expected_head=head).valid)
            target_idx = rng.randrange(len(events))
            mut_events = [dict(e) for e in events]
            orig_d = mut_events[target_idx]["response_digest"]
            mut_events[target_idx]["response_digest"] = ("0" if orig_d[0] != "0" else "1") + orig_d[1:]
            self.assertFalse(verify_hash_chain(commitment, f"ep-prop-{trial}", mut_events, expected_head=head).valid)


if __name__ == "__main__":
    unittest.main()
