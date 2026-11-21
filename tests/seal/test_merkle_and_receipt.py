"""Tests for RFC-6962 Merkle tree & offline receipts (Phase 9, Task 9.6 — REQ-SEAL-020..023)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from contracts.loader import validate_instance
from seal.commitment import create_commitment_bundle, deterministic_fixture_salt
from seal.hashchain import HashChainBuilder
from seal.merkle import EMPTY_TREE_ROOT, MerkleTree, verify_inclusion_proof
from seal.receipt import (
    build_lineage_digests,
    build_receipt,
    compute_code_version_hash,
    compute_manifest_hash,
    seal_receipt_batch,
    verify_receipt_offline,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VALID_TRUTH_PATH = REPO_ROOT / "tests" / "fixtures" / "valid" / "truth.json"
VALID_MANIFEST_PATH = REPO_ROOT / "tests" / "fixtures" / "valid" / "episode_manifest.json"


def _h(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class TestMerkleAndReceipts(unittest.TestCase):
    def test_empty_single_even_and_odd_merkle_trees(self) -> None:
        empty = MerkleTree.from_leaves([])
        self.assertEqual(empty.root, EMPTY_TREE_ROOT)
        self.assertEqual(empty.leaf_count, 0)

        for count in (1, 2, 3, 4, 5, 7, 8, 10, 20):
            leaves = [_h(f"leaf-{count}-{i}") for i in range(count)]
            tree = MerkleTree.from_leaves(leaves)
            self.assertEqual(tree.leaf_count, count)
            for idx, leaf in enumerate(leaves):
                proof = tree.inclusion_proof(idx)
                self.assertTrue(
                    verify_inclusion_proof(leaf, idx, count, proof, tree.root),
                    msg=f"valid proof failed for idx={idx}, count={count}",
                )
                # Wrong leaf index rejected
                if count > 1:
                    other_idx = (idx + 1) % count
                    self.assertFalse(
                        verify_inclusion_proof(leaf, other_idx, count, proof, tree.root)
                    )
                # Wrong leaf_count rejected
                self.assertFalse(
                    verify_inclusion_proof(leaf, idx, count + 1, proof, tree.root)
                )
                # Mutated leaf rejected
                self.assertFalse(
                    verify_inclusion_proof(_h("tampered"), idx, count, proof, tree.root)
                )

    def test_odd_leaf_promotion_prevents_duplication_collision(self) -> None:
        # Classic CVE-2012-2459 check: [A, B, C] must NOT collide with [A, B, C, C]!
        a, b, c = _h("A"), _h("B"), _h("C")
        t3 = MerkleTree.from_leaves([a, b, c])
        t4_dup = MerkleTree.from_leaves([a, b, c, c])
        self.assertNotEqual(t3.root, t4_dup.root)

        # Mutating any single leaf changes root (REQ-SEAL-022)
        t3_mut = MerkleTree.from_leaves([a, _h("B-mut"), c])
        self.assertNotEqual(t3.root, t3_mut.root)

    def test_receipt_offline_verification_and_batch_sealing(self) -> None:
        truth_item = json.loads(VALID_TRUTH_PATH.read_text(encoding="utf-8"))
        manifest_template = json.loads(VALID_MANIFEST_PATH.read_text(encoding="utf-8"))
        code_hash = compute_code_version_hash()

        receipts: list[dict] = []
        manifests: list[dict] = []
        chains: list[list[dict]] = []
        salts: list[str] = []

        for idx in range(3):
            ep_id = f"ep-batch-{idx:03d}"
            salt_hex, salt_mode = deterministic_fixture_salt(ep_id)
            salts.append(salt_hex)
            bundle, _ = create_commitment_bundle(
                ep_id,
                [truth_item],
                salt_hex=salt_hex,
                salt_mode=salt_mode,
            )
            manifest = dict(manifest_template)
            manifest["episode_id"] = ep_id
            manifest["truth_commitment"] = bundle.truth_commitment
            m_hash = compute_manifest_hash(manifest)

            hb = HashChainBuilder(truth_commitment=bundle.truth_commitment, episode_id=ep_id)
            hb.append(event_type="reset", action_payload={"i": idx}, response_payload={"ok": True}, logical_step=0)
            hb.append(event_type="submit", action_payload={"findings": []}, response_payload={"ok": True}, logical_step=0)
            ev_dicts = [e.to_dict() for e in hb.events]

            lineage = build_lineage_digests(
                generator_version="twinledger-gen@1.0.0",
                config_hash=manifest["config_hash"],
                public_manifest_hash=m_hash,
                truth_commitment=bundle.truth_commitment,
                trajectory_head=hb.head,
            )
            rcpt = build_receipt(
                episode_id=ep_id,
                code_version_hash=code_hash,
                config_hash=manifest["config_hash"],
                public_manifest_hash=m_hash,
                truth_commitment=bundle.truth_commitment,
                trajectory_head=hb.head,
                policy_identifier="silent_v1",
                lineage=lineage,
            )
            self.assertEqual(validate_instance("receipt", rcpt), [])
            receipts.append(rcpt)
            manifests.append(manifest)
            chains.append(ev_dicts)

        batch_root, sealed_batch = seal_receipt_batch(receipts)
        self.assertEqual(len(sealed_batch), 3)

        for idx in range(3):
            v = verify_receipt_offline(
                sealed_batch[idx],
                manifest=manifests[idx],
                trajectory_events=chains[idx],
                revealed_truths=[truth_item],
                revealed_salt_hex=salts[idx],
                salt_mode="TEST_FIXTURE",
                expected_merkle_root=batch_root,
            )
            self.assertTrue(v.valid, msg=f"batch receipt[{idx}] failed: {v.errors}")
            self.assertTrue(v.schema_ok)
            self.assertTrue(v.manifest_ok)
            self.assertTrue(v.commitment_ok)
            self.assertTrue(v.trajectory_ok)
            self.assertTrue(v.merkle_ok)

            # Tampering trajectory_head invalidates Merkle & trajectory checks
            bad_rcpt = dict(sealed_batch[idx])
            bad_rcpt["trajectory_head"] = _h("forged-head")
            v_bad = verify_receipt_offline(
                bad_rcpt,
                manifest=manifests[idx],
                trajectory_events=chains[idx],
                expected_merkle_root=batch_root,
            )
            self.assertFalse(v_bad.valid)
            self.assertFalse(v_bad.trajectory_ok)
            self.assertFalse(v_bad.merkle_ok)

        # Also verify offline CLI (`python3 -m seal.cli verify-receipt`)
        with tempfile.TemporaryDirectory(prefix="tl_seal_cli_") as tmp:
            td = Path(tmp)
            (td / "receipt.json").write_text(json.dumps(sealed_batch[0]), encoding="utf-8")
            (td / "manifest.json").write_text(json.dumps(manifests[0]), encoding="utf-8")
            (td / "traj.json").write_text(json.dumps(chains[0]), encoding="utf-8")
            (td / "truth.json").write_text(json.dumps([truth_item]), encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "seal.cli",
                    "verify-receipt",
                    "--receipt",
                    str(td / "receipt.json"),
                    "--manifest",
                    str(td / "manifest.json"),
                    "--trajectory",
                    str(td / "traj.json"),
                    "--truth",
                    str(td / "truth.json"),
                    "--salt",
                    salts[0],
                    "--merkle-root",
                    batch_root,
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=20.0,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            parsed = json.loads(proc.stdout)
            self.assertTrue(parsed["valid"])


if __name__ == "__main__":
    unittest.main()
