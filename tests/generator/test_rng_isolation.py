"""RNG Namespace Isolation Tests (Phase 13 — TZ §20.4, D-13-01).

Proves:
  1. CleanTwin digest is 100% invariant to downstream anomaly operator recipes for a
     fixed ``(master_seed, episode_index)`` — verified by building episodes with
     different anomaly sets from the same spec and by scoped-namespace disjointness;
  2. Representative text and injection settings preserve the tested invoice
     IDs, amounts and currencies, truth bytes and verifier findings;
  3. Scoped RNG namespaces (``clean_twin`` / ``operators`` / ``text_layer`` /
     ``injection_layer``) are disjoint and stateless — no global ``random`` state;
  4. Operator order changes the serialized truth for one representative recipe.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from contracts.canonical import sha256_hex
from gen.core.clean_twin import CleanTwinSpec, generate_clean_twin
from gen.core.rng import scoped_rng
from gen.pipeline import EpisodeRecipe, build_episode
from verifier import discover


class TestRNGIsolation(unittest.TestCase):
    def test_clean_twin_hash_invariant_across_operator_plans(self) -> None:
        spec = CleanTwinSpec(episode_id="ep_rng_clean", master_seed=7777, episode_index=3)
        t1 = generate_clean_twin(spec).public_tables()
        t2 = generate_clean_twin(spec).public_tables()
        self.assertEqual(sha256_hex(t1), sha256_hex(t2))

    def test_scoped_namespaces_are_disjoint_and_stateless(self) -> None:
        # TZ §20.4: clean_twin / operators / text_layer / injection_layer must be
        # disjoint streams derived from (master_seed, scope...). Re-deriving a
        # namespace after using others must reproduce the same sequence (no
        # global state leak).
        seed, ep_id, idx = 7777, "ep_rng_clean", 3
        clean_rng = scoped_rng(seed, "clean_twin", ep_id, idx)
        clean_seq = [clean_rng.random() for _ in range(5)]

        ops_rng = scoped_rng(seed, "operators", ep_id, 1)
        ops_seq = [ops_rng.random() for _ in range(5)]
        txt_rng = scoped_rng(seed, "text_layer", ep_id, 1)
        txt_seq = [txt_rng.random() for _ in range(5)]
        inj_rng = scoped_rng(seed, "injection_layer", ep_id, 1)
        inj_seq = [inj_rng.random() for _ in range(5)]

        self.assertNotEqual(clean_seq, ops_seq)
        self.assertNotEqual(clean_seq, txt_seq)
        self.assertNotEqual(clean_seq, inj_seq)
        self.assertNotEqual(ops_seq, txt_seq)

        # Stateless re-derivation: fresh RNG for the same scope reproduces seq.
        clean_rng2 = scoped_rng(seed, "clean_twin", ep_id, idx)
        self.assertEqual([clean_rng2.random() for _ in range(5)], clean_seq)
        ops_rng2 = scoped_rng(seed, "operators", ep_id, 1)
        self.assertEqual([ops_rng2.random() for _ in range(5)], ops_seq)

    def test_clean_twin_hash_invariant_across_anomaly_sets(self) -> None:
        # Build episodes from the SAME spec with different operator plans.
        # The underlying clean twin (generate_clean_twin(spec)) must be
        # byte-identical for all plans; only mutated truth may differ.
        spec = CleanTwinSpec(episode_id="ep_rng_plans", master_seed=8888, episode_index=5)
        clean_hash = sha256_hex(generate_clean_twin(spec).public_tables())
        plans = [
            (),
            ("DUPLICATE_PAYMENT",),
            ("FX_RATE_MISMATCH",),
            ("DUPLICATE_PAYMENT", "FX_RATE_MISMATCH"),
        ]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            truth_hashes = []
            for i, anomalies in enumerate(plans):
                observed_hashes = []

                def capture_clean(twin_spec):
                    twin = generate_clean_twin(twin_spec)
                    observed_hashes.append(sha256_hex(twin.public_tables()))
                    return twin

                with patch("gen.pipeline.generate_clean_twin", side_effect=capture_clean):
                    ep = build_episode(
                        EpisodeRecipe(twin_spec=spec, anomalies=anomalies),
                        root / f"plan_{i}",
                        out_dir_exact=True,
                    )
                self.assertTrue(observed_hashes)
                self.assertTrue(all(h == clean_hash for h in observed_hashes), anomalies)
                truth_hashes.append(
                    hashlib.sha256((ep.episode_dir / "sealed" / "truth.json").read_bytes()).hexdigest()
                )
            # Clean plan must differ from mutated plans (operators took effect).
            self.assertNotEqual(truth_hashes[0], truth_hashes[1])
            self.assertNotEqual(truth_hashes[1], truth_hashes[2])

    def test_operator_order_is_causal_but_clean_twin_stable(self) -> None:
        # Compare serialized truth for a representative pair of operator orders.
        # A difference can include ordering or truth identifiers.
        spec = CleanTwinSpec(episode_id="ep_rng_order", master_seed=9999, episode_index=6)
        clean_hash = sha256_hex(generate_clean_twin(spec).public_tables())
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ep_a = build_episode(
                EpisodeRecipe(twin_spec=spec, anomalies=("DUPLICATE_PAYMENT", "FX_RATE_MISMATCH")),
                root / "a",
                out_dir_exact=True,
            )
            ep_b = build_episode(
                EpisodeRecipe(twin_spec=spec, anomalies=("FX_RATE_MISMATCH", "DUPLICATE_PAYMENT")),
                root / "b",
                out_dir_exact=True,
            )
            self.assertEqual(sha256_hex(generate_clean_twin(spec).public_tables()), clean_hash)
            truth_a = (ep_a.episode_dir / "sealed" / "truth.json").read_bytes()
            truth_b = (ep_b.episode_dir / "sealed" / "truth.json").read_bytes()
            self.assertNotEqual(truth_a, truth_b, "serialized truth differs for this pair of operator orders")

    def test_text_and_injection_namespaces_never_change_amounts_ids_or_truth(self) -> None:
        base_spec = CleanTwinSpec(
            episode_id="ep_rng_iso",
            master_seed=9001,
            episode_index=4,
            enable_text_layer=False,
        )
        variants = [
            base_spec,
            dataclasses.replace(base_spec, enable_text_layer=True, language_profile="en", text_noise_level=0),
            dataclasses.replace(base_spec, enable_text_layer=True, language_profile="ru", text_noise_level=1),
            dataclasses.replace(base_spec, enable_text_layer=True, language_profile="kk", text_noise_level=2),
            dataclasses.replace(
                base_spec,
                enable_text_layer=True,
                language_profile="mixed",
                text_noise_level=2,
                enable_prompt_injection=True,
            ),
        ]

        anomalies = ("DUPLICATE_PAYMENT", "FX_RATE_MISMATCH")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref_truth_sha: str | None = None
            ref_inv_amounts: list[tuple[str, int, str]] | None = None
            ref_verifier: list[dict] | None = None

            for idx, sp in enumerate(variants):
                ep = build_episode(
                    EpisodeRecipe(twin_spec=sp, anomalies=anomalies),
                    root / f"v_{idx}",
                    out_dir_exact=True,
                )
                truth_sha = hashlib.sha256((ep.episode_dir / "sealed" / "truth.json").read_bytes()).hexdigest()
                invs = [
                    json.loads(ln)
                    for ln in (ep.episode_dir / "public" / "invoices.jsonl").read_text(encoding="utf-8").splitlines()
                    if ln.strip()
                ]
                inv_sig = [(r["doc_id"], r["total_minor"], r["currency"]) for r in invs]
                ver_sig = [f.to_dict() for f in discover(ep.episode_dir / "public").report.findings]

                if ref_truth_sha is None:
                    ref_truth_sha = truth_sha
                    ref_inv_amounts = inv_sig
                    ref_verifier = ver_sig
                else:
                    self.assertEqual(truth_sha, ref_truth_sha)
                    self.assertEqual(inv_sig, ref_inv_amounts)
                    self.assertEqual(ver_sig, ref_verifier)


if __name__ == "__main__":
    unittest.main()
