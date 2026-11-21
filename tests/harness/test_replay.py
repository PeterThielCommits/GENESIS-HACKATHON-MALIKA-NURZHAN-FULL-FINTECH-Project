"""Tests for fresh-process trajectory replay & tamper detection (Phase 9, Task 9.7 — REQ-SEAL-030..031)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gen.pipeline import build_episode, default_dataset_recipes
from harness.replay import replay_episode, run_replay_verification_suite
from harness.runner import run_closed_eval_batch
from harness.sandbox import REPO_ROOT


class TestFreshProcessReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="tl_p9_replay_")
        root = Path(cls._tmp.name)
        recipes = default_dataset_recipes("dev", master_seed=2025)
        cls.ep_clean = build_episode(recipes[0], root).episode_dir
        cls.ep_dup = build_episode(recipes[1], root).episode_dir
        cls.art_dir = root / "batch_art"

        cls.merkle_root, cls.batch_results = run_closed_eval_batch(
            runs=[
                (
                    cls.ep_clean,
                    [sys.executable, "-m", "harness.reference_policies", "--policy", "silent_v1"],
                    "silent_v1",
                ),
                (
                    cls.ep_dup,
                    [sys.executable, "-m", "harness.reference_policies", "--policy", "rule_auditor_v1"],
                    "rule_auditor_v1",
                ),
            ],
            artifacts_dir=cls.art_dir,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_fresh_process_replay_is_byte_and_reward_identical(self) -> None:
        for run_res, ep_dir in zip(self.batch_results, (self.ep_clean, self.ep_dup)):
            rep = replay_episode(
                episode_dir=ep_dir,
                trajectory_path=run_res.trajectory_path,
                submission_path=run_res.submission_path,
                receipt_path=run_res.receipt_path,
                score_report_path=run_res.score_report_path,
            )
            self.assertTrue(rep.matched, msg=f"replay mismatch: {rep.mismatches}")
            self.assertTrue(rep.response_bytes_identical)
            self.assertTrue(rep.event_hashes_identical)
            self.assertTrue(rep.reward_identical)
            self.assertTrue(rep.offline_receipt_valid)
            self.assertEqual(rep.recorded_head, rep.replayed_head)

    def test_replay_detects_tampered_response_hash_and_public_snapshot(self) -> None:
        run0 = self.batch_results[0]
        orig_lines = run0.trajectory_path.read_text(encoding="utf-8").splitlines()

        with tempfile.TemporaryDirectory(prefix="tl_tamper_") as td:
            troot = Path(td)

            # 1. Tamper canonical_response_json of step 1
            bad_resp_path = troot / "bad_resp.trajectory.jsonl"
            row1 = json.loads(orig_lines[1])
            row1["canonical_response_json"] = '{"error":null,"ok":true,"protocol_version":"1.0","request_id":"tampered","result":{}}'
            bad_resp_path.write_text(
                "\n".join([orig_lines[0], json.dumps(row1), *orig_lines[2:]]) + "\n",
                encoding="utf-8",
            )
            rep_bad_resp = replay_episode(
                episode_dir=self.ep_clean,
                trajectory_path=bad_resp_path,
            )
            self.assertFalse(rep_bad_resp.matched)
            self.assertFalse(rep_bad_resp.response_bytes_identical)

            # 2. Tamper chain_head_after of final event
            bad_head_path = troot / "bad_head.trajectory.jsonl"
            last = json.loads(orig_lines[-1])
            last["chain_head_after"] = "f" * 64
            bad_head_path.write_text(
                "\n".join([*orig_lines[:-1], json.dumps(last)]) + "\n",
                encoding="utf-8",
            )
            rep_bad_head = replay_episode(
                episode_dir=self.ep_clean,
                trajectory_path=bad_head_path,
            )
            self.assertFalse(rep_bad_head.matched)
            self.assertFalse(rep_bad_head.event_hashes_identical)

            # 3. Tamper public snapshot file on disk
            ep_copy = troot / "ep_copy"
            shutil.copytree(self.ep_clean, ep_copy)
            inv_file = ep_copy / "public" / "company.json"
            comp = json.loads(inv_file.read_text(encoding="utf-8"))
            comp["legal_name"] = "TAMPERED CORP"
            inv_file.write_text(json.dumps(comp), encoding="utf-8")

            rep_bad_pub = replay_episode(
                episode_dir=ep_copy,
                trajectory_path=run0.trajectory_path,
            )
            self.assertFalse(rep_bad_pub.matched)

            # 4. Tamper sealed/truth.json on disk -> replay scorer detects commitment break (exit 4)
            ep_bad_truth = troot / "ep_bad_truth"
            shutil.copytree(self.ep_dup, ep_bad_truth)
            (ep_bad_truth / "sealed" / "truth.json").write_text("[]\n", encoding="utf-8")
            rep_bad_truth = replay_episode(
                episode_dir=ep_bad_truth,
                trajectory_path=self.batch_results[1].trajectory_path,
                submission_path=self.batch_results[1].submission_path,
            )
            self.assertFalse(rep_bad_truth.matched)
            self.assertFalse(rep_bad_truth.reward_identical)

    def test_cli_single_episode_and_verify_suite(self) -> None:
        run0 = self.batch_results[0]
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "harness.replay",
                "--episode-dir",
                str(self.ep_clean),
                "--trajectory",
                str(run0.trajectory_path),
                "--receipt",
                str(run0.receipt_path),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30.0,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        out = json.loads(proc.stdout)
        self.assertTrue(out["matched"])

        with tempfile.TemporaryDirectory(prefix="tl_suite_out_") as td:
            rep_file = Path(td) / "replay_report.json"
            report = run_replay_verification_suite(output_report_path=rep_file)
            self.assertEqual(report["status"], "PASS")
            self.assertTrue(report["all_byte_identical"])
            self.assertTrue(report["all_hashes_identical"])
            self.assertTrue(report["all_rewards_identical"])
            self.assertTrue(report["all_receipts_verified_offline"])
            self.assertTrue(rep_file.is_file())


if __name__ == "__main__":
    unittest.main()
