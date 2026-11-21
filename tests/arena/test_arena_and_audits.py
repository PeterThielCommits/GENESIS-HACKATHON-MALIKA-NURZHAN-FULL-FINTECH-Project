"""Integration tests for Phase 12 (Arena, 22 Attacks, AutoHacker, Shortcut Audit, Canary Fuzzer)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from arena.attacks.catalog import ATTACK_SPECS
from arena.autohacker import run_arena_and_autohacker
from arena.policies.catalog import PUBLIC_BASELINE_IDS
from judge.canary_fuzzer import run_canary_and_api_fuzzer
from judge.shortcut_audit import run_shortcut_audit


class TestPhase12ArenaAndAudits(unittest.TestCase):
    def test_baseline_and_attack_catalogs_meet_tz_counts_and_separation(self) -> None:
        self.assertEqual(len(PUBLIC_BASELINE_IDS), 7)
        self.assertNotIn("oracle_test_only", PUBLIC_BASELINE_IDS)
        self.assertGreaterEqual(len(ATTACK_SPECS), 22)

    def test_autohacker_arena_defends_all_22_attacks_and_isolates_splits(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rep = run_arena_and_autohacker(output_path=Path(td) / "arena.json")
            self.assertEqual(rep["status"], "PASS")
            self.assertEqual(rep["split_isolation"]["cross_split_group_overlap"], 0)
            self.assertFalse(rep["split_isolation"]["heldout_used_for_tuning"])
            self.assertTrue(rep["attacks_heldout"]["all_defended"])

    def test_shortcut_audit_auc_within_bound_and_side_channels_uniform(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rep = run_shortcut_audit(output_path=Path(td) / "shortcut.json")
            self.assertEqual(rep["status"], "PASS")
            self.assertLessEqual(rep["metadata_classifier"]["macro_roc_auc"], 0.55)
            self.assertTrue(rep["side_channel_audit"]["error_surface_uniform"])

    def test_canary_and_api_fuzzer_zero_hits_across_10_channels(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rep = run_canary_and_api_fuzzer(fuzz_seed=20261121, output_path=Path(td) / "canary.json")
            self.assertEqual(rep["status"], "PASS")
            self.assertEqual(rep["canary_summary"]["total_canary_hits"], 0)
            self.assertTrue(rep["canary_summary"]["raw_canary_strings_omitted_from_report"])
            self.assertTrue(rep["api_fuzz_summary"]["all_handled_cleanly"])


if __name__ == "__main__":
    unittest.main()
