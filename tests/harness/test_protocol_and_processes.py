"""Tests for JSONL protocol, multi-process CLOSED_EVAL, and post-termination scorer (Tasks 9.1–9.3)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from gen.pipeline import build_episode, default_dataset_recipes
from harness.env_process import EnvSubprocess
from harness.protocol import (
    MAX_JSONL_LINE_BYTES,
    ProtocolError,
    format_policy_reset_frame,
    format_policy_response_frame,
    format_policy_terminate_frame,
    validate_tool_request_line,
)
from harness.runner import run_closed_eval_episode
from harness.scorer_process import ScorerPrematureStartError, run_scorer_subprocess


class TestProtocolAndProcesses(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="tl_p9_proc_")
        root = Path(cls._tmp.name)
        recipes = default_dataset_recipes("dev", master_seed=2025)
        cls.ep_clean = build_episode(recipes[0], root).episode_dir
        cls.ep_dup = build_episode(recipes[1], root).episode_dir
        cls.work_dir = root / "artifacts"
        cls.work_dir.mkdir()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_protocol_frames_and_request_validation(self) -> None:
        rst = json.loads(format_policy_reset_frame({"mode": "CLOSED_EVAL"}))
        self.assertEqual(rst["protocol_version"], "1.0")
        self.assertEqual(rst["type"], "reset")

        valid_resp = {
            "protocol_version": "1.0",
            "request_id": "r1",
            "ok": True,
            "result": {"accepted": True},
            "error": None,
        }
        rf = json.loads(format_policy_response_frame(valid_resp))
        self.assertEqual(rf["type"], "response")

        with self.assertRaises(ProtocolError):
            format_policy_response_frame({"bad": "response"})

        tf = json.loads(format_policy_terminate_frame("submitted"))
        self.assertEqual(tf["type"], "terminate")

        ok_req, err = validate_tool_request_line(
            json.dumps(
                {
                    "protocol_version": "1.0",
                    "request_id": "q1",
                    "action": {"tool": "calc", "args": {"expression": "1+1"}},
                }
            )
        )
        self.assertIsNotNone(ok_req)
        self.assertIsNone(err)

        _, err_bad = validate_tool_request_line("{not json")
        self.assertIsNotNone(err_bad)

        _, err_big = validate_tool_request_line("a" * (MAX_JSONL_LINE_BYTES + 10))
        self.assertIsNotNone(err_big)

    def test_closed_eval_clean_mutated_and_truncated_runs(self) -> None:
        # 1. Clean episode + silent_v1 -> F1=1, terminated=True, VERIFIED receipt
        res_clean = run_closed_eval_episode(
            episode_dir=self.ep_clean,
            policy_argv=[sys.executable, "-m", "harness.reference_policies", "--policy", "silent_v1"],
            policy_id="silent_v1",
            artifacts_dir=self.work_dir / "clean_run",
        )
        self.assertTrue(res_clean.terminated)
        self.assertFalse(res_clean.truncated)
        self.assertFalse(res_clean.no_submit)
        self.assertEqual(res_clean.steps_used, 2)
        self.assertTrue(res_clean.lifecycle.strictly_ordered)
        self.assertEqual(res_clean.receipt["verification_status"], "VERIFIED")
        self.assertEqual(res_clean.receipt["x_twinledger_salt_reveal_ref"], "SEALED")
        self.assertEqual(
            Fraction(res_clean.score_report["contract_v1_score"]["reward_breakdown"]["f1_exact"]),
            Fraction(1),
        )

        # 2. Duplicate payment episode + rule_auditor_v1 -> exact match F1=1
        res_dup = run_closed_eval_episode(
            episode_dir=self.ep_dup,
            policy_argv=[sys.executable, "-m", "harness.reference_policies", "--policy", "rule_auditor_v1"],
            policy_id="rule_auditor_v1",
            artifacts_dir=self.work_dir / "dup_run",
        )
        self.assertTrue(res_dup.terminated)
        self.assertTrue(res_dup.lifecycle.strictly_ordered)
        self.assertEqual(res_dup.receipt["verification_status"], "VERIFIED")
        self.assertEqual(
            Fraction(res_dup.score_report["contract_v1_score"]["reward_breakdown"]["f1_exact"]),
            Fraction(1),
        )
        self.assertEqual(res_dup.score_report["official_score"]["f1"], 1.0)

        # 3. Budget exhaustion without submit -> truncated=True, no_submit=True, TRUNCATED_NO_SUBMIT
        small_cfg = self.work_dir / "small_budget_env.json"
        small_cfg.write_text(
            json.dumps(
                {
                    "mode": "CLOSED_EVAL",
                    "max_steps": 4,
                    "max_page_size": 50,
                    "max_findings": 20,
                    "max_evidence_ids": 20,
                    "max_request_bytes": 65536,
                    "max_calc_expression_length": 500,
                    "max_calc_ast_nodes": 100,
                    "submit_counts_as_step": False,
                }
            ),
            encoding="utf-8",
        )
        res_trunc = run_closed_eval_episode(
            episode_dir=self.ep_clean,
            policy_argv=[sys.executable, "-m", "harness.reference_policies", "--policy", "truncate_exhaust_v1"],
            policy_id="truncate_exhaust_v1",
            artifacts_dir=self.work_dir / "trunc_run",
            env_config_path=small_cfg,
        )
        self.assertFalse(res_trunc.terminated)
        self.assertTrue(res_trunc.truncated)
        self.assertTrue(res_trunc.no_submit)
        self.assertEqual(res_trunc.steps_used, 4)
        self.assertEqual(
            res_trunc.score_report["contract_v1_score"]["diagnostics"]["audit_status"],
            "TRUNCATED_NO_SUBMIT",
        )

    def test_scorer_premature_start_rejected(self) -> None:
        dummy = self.work_dir / "dummy.json"
        dummy.write_text("{}", encoding="utf-8")

        # 1. env_alive=True must raise ScorerPrematureStartError
        with self.assertRaises(ScorerPrematureStartError):
            run_scorer_subprocess(
                episode_dir=self.ep_clean,
                submission_path=dummy,
                trajectory_path=dummy,
                policy_id="p",
                output_receipt_path=self.work_dir / "r.json",
                output_score_path=self.work_dir / "s.json",
                env_alive=True,
                policy_alive=False,
                env_exited_ns=100,
                policy_exited_ns=100,
            )

        # 2. policy_alive=True must raise ScorerPrematureStartError
        with self.assertRaises(ScorerPrematureStartError):
            run_scorer_subprocess(
                episode_dir=self.ep_clean,
                submission_path=dummy,
                trajectory_path=dummy,
                policy_id="p",
                output_receipt_path=self.work_dir / "r.json",
                output_score_path=self.work_dir / "s.json",
                env_alive=False,
                policy_alive=True,
                env_exited_ns=100,
                policy_exited_ns=100,
            )

        # 3. Missing exit timestamps must raise ScorerPrematureStartError
        with self.assertRaises(ScorerPrematureStartError):
            run_scorer_subprocess(
                episode_dir=self.ep_clean,
                submission_path=dummy,
                trajectory_path=dummy,
                policy_id="p",
                output_receipt_path=self.work_dir / "r.json",
                output_score_path=self.work_dir / "s.json",
                env_alive=False,
                policy_alive=False,
                env_exited_ns=None,
                policy_exited_ns=100,
            )

    def test_open_dev_rejected_when_closed_eval_required(self) -> None:
        open_cfg = self.work_dir / "open_dev_env.json"
        open_cfg.write_text(json.dumps({"mode": "OPEN_DEV", "max_steps": 10}), encoding="utf-8")
        proc = EnvSubprocess(
            self.ep_clean / "public",
            env_config_path=open_cfg,
            require_closed_eval=True,
        )
        import time

        with self.assertRaises(ProtocolError):
            proc.start(deadline_monotonic=time.monotonic() + 10.0)
        self.assertFalse(proc.is_alive)


if __name__ == "__main__":
    unittest.main()
