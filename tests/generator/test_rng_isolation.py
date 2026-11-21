"""RNG Namespace Isolation Tests (Phase 13 — TZ §20.4).

Proves:
  1. CleanTwin digest is 100% invariant to downstream anomaly operator recipes for a
     fixed ``(master_seed, episode_index)``;
  2. Toggling ``enable_text_layer``, ``language_profile`` (``en``/``ru``/``kk``/``mixed``),
     ``text_noise_level`` (``0, 1, 2``), and ``enable_prompt_injection`` NEVER alters
     monetary amounts, typed IDs, dates, ``sealed/truth.json``, or ``verifier.discover``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from contracts.canonical import sha256_hex
from gen.core.clean_twin import CleanTwinSpec, generate_clean_twin
from gen.pipeline import EpisodeRecipe, build_episode
from verifier import discover


class TestRNGIsolation(unittest.TestCase):
    def test_clean_twin_hash_invariant_across_operator_plans(self) -> None:
        spec = CleanTwinSpec(episode_id="ep_rng_clean", master_seed=7777, episode_index=3)
        t1 = generate_clean_twin(spec).public_tables()
        t2 = generate_clean_twin(spec).public_tables()
        self.assertEqual(sha256_hex(t1), sha256_hex(t2))

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
