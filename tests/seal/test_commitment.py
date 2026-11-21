"""Tests for commit-reveal primitives (Phase 9, Task 9.4 — REQ-SEAL-010..013)."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from gen.pipeline import EpisodeRecipe, build_episode, default_dataset_recipes
from gen.truth import compute_truth_commitment
from seal.commitment import (
    COMMITMENT_INTEGRITY_NOTE,
    CommitmentBundle,
    compute_commitment,
    create_commitment_bundle,
    deterministic_fixture_salt,
    generate_secret_salt,
    verify_episode_commitment_from_disk,
    verify_reveal,
)

VALID_TRUTH_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "valid" / "truth.json"
)


class TestCommitReveal(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_truth = json.loads(VALID_TRUTH_FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_csprng_salt_generation_and_bounds(self) -> None:
        s1 = generate_secret_salt(32)
        s2 = generate_secret_salt(32)
        self.assertEqual(len(s1), 64)
        self.assertEqual(len(s2), 64)
        self.assertNotEqual(s1, s2)
        with self.assertRaises(ValueError):
            generate_secret_salt(8)
        with self.assertRaises(ValueError):
            generate_secret_salt(True)  # type: ignore[arg-type]

    def test_fixture_salt_mode_explicitly_marked(self) -> None:
        salt_a, mode_a = deterministic_fixture_salt("ep-fixture-01")
        salt_b, mode_b = deterministic_fixture_salt("ep-fixture-01")
        salt_c, _ = deterministic_fixture_salt("ep-fixture-02")
        self.assertEqual(mode_a, "TEST_FIXTURE")
        self.assertEqual(mode_b, "TEST_FIXTURE")
        self.assertEqual(salt_a, salt_b)
        self.assertNotEqual(salt_a, salt_c)
        with self.assertRaises(ValueError):
            deterministic_fixture_salt("   ")

    def test_byte_identical_with_generator_truth_commitment(self) -> None:
        salt = generate_secret_salt(32)
        for truths in ([], [self.sample_truth]):
            c_gen = compute_truth_commitment(truths, salt)
            c_seal = compute_commitment(truths, salt)
            self.assertEqual(c_gen, c_seal)

    def test_create_bundle_and_verify_reveal_roundtrip(self) -> None:
        bundle, secret_salt = create_commitment_bundle(
            "ep-commit-001",
            [self.sample_truth],
            salt_mode="PRODUCTION_SECRET",
        )
        pub = bundle.to_public_dict()
        self.assertNotIn("salt", json.dumps(pub))
        self.assertTrue(pub["created_before_policy"])

        res = verify_reveal(
            bundle.truth_commitment,
            [self.sample_truth],
            secret_salt,
            salt_mode="PRODUCTION_SECRET",
        )
        self.assertTrue(res.verified)
        self.assertEqual(res.truth_count, 1)
        self.assertEqual(res.errors, ())
        self.assertEqual(res.integrity_scope_note, COMMITMENT_INTEGRITY_NOTE)

        # Key-order permutation inside truth dict preserves canonical commitment
        reordered_truth = {k: self.sample_truth[k] for k in reversed(list(self.sample_truth.keys()))}
        res_perm = verify_reveal(bundle.truth_commitment, [reordered_truth], secret_salt)
        self.assertTrue(res_perm.verified)

    def test_tampered_truth_or_wrong_salt_or_invalid_schema_rejected(self) -> None:
        bundle, secret_salt = create_commitment_bundle("ep-commit-002", [self.sample_truth])

        # 1. Wrong salt
        wrong_salt = generate_secret_salt(32)
        r_salt = verify_reveal(bundle.truth_commitment, [self.sample_truth], wrong_salt)
        self.assertFalse(r_salt.verified)

        # 2. Mutated amount (+1 minor unit)
        tampered = copy.deepcopy(self.sample_truth)
        tampered["amount_minor"] += 1
        r_amt = verify_reveal(bundle.truth_commitment, [tampered], secret_salt)
        self.assertFalse(r_amt.verified)

        # 3. Empty truth substituted for non-empty truth
        r_empty = verify_reveal(bundle.truth_commitment, [], secret_salt)
        self.assertFalse(r_empty.verified)

        # 4. Duplicate truth_id rejected
        r_dup = verify_reveal(bundle.truth_commitment, [self.sample_truth, self.sample_truth], secret_salt)
        self.assertFalse(r_dup.verified)

        # 5. Schema-invalid truth rejected
        bad_schema = copy.deepcopy(self.sample_truth)
        bad_schema["unknown_extra_field"] = 123
        r_schema = verify_reveal(bundle.truth_commitment, [bad_schema], secret_salt)
        self.assertFalse(r_schema.verified)

        # 6. Commitment created_before_policy=False rejected
        with self.assertRaises(ValueError):
            CommitmentBundle(
                episode_id="ep-bad",
                truth_commitment=bundle.truth_commitment,
                created_before_policy=False,
            )

    def test_generated_episodes_verify_from_disk(self) -> None:
        recipes = default_dataset_recipes("dev", master_seed=2025)[:3]
        with tempfile.TemporaryDirectory(prefix="tl_commit_disk_") as tmp:
            out = Path(tmp)
            for recipe in recipes:
                ep = build_episode(recipe, out)
                res = verify_episode_commitment_from_disk(ep.episode_dir, salt_mode="TEST_FIXTURE")
                self.assertTrue(res.verified, msg=f"failed for {ep.episode_id}: {res.errors}")

                # Corrupt sealed/truth.json on disk and ensure reveal fails
                truth_file = ep.episode_dir / "sealed" / "truth.json"
                truth_file.write_text(json.dumps([self.sample_truth]), encoding="utf-8")
                res_bad = verify_episode_commitment_from_disk(ep.episode_dir, salt_mode="TEST_FIXTURE")
                self.assertFalse(res_bad.verified)


if __name__ == "__main__":
    unittest.main()
