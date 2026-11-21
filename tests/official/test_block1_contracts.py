"""Block 1 mirror tests: Contract checks C01..C20 (Genesis FinTech 2026-11-20)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import judge_adapter
from adapter.official_env import OfficialJudgeEnv
from harness.isolated_runner import run_isolated_public_policy


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestBlock1ContractsC01ToC20(unittest.TestCase):
    """Exact verification of official contract tests C01..C20."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="tl_block1_")
        root = Path(cls._tmp.name)
        cls.dir_c = str(root / "fixture_C")
        cls.dir_e = str(root / "fixture_E")
        cls.dir_l = str(root / "fixture_L")
        judge_adapter.generate_episode(2026, {"scenario": "C"}, cls.dir_c)
        judge_adapter.generate_episode(2026, {"scenario": "E"}, cls.dir_e)
        judge_adapter.generate_episode(2026, {"scenario": "L"}, cls.dir_l)

        # Pick existing R1 and D1 from fixture C (judge-side inspection of public data)
        env = judge_adapter.make_env()
        env.reset(seed=2026, config={"mode": "closed", "episode_dir": cls.dir_c})
        obs, _, _, _, _ = env.step({"name": "list_records", "args": {"table": "invoices", "cursor": None, "limit": 5}})
        cls.r1_id = obs["result"]["records"][0]["doc_id"]
        cls.d1_id = cls.r1_id
        cls.u_id = "NONEXISTENT_ID_999999_ABSENT"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _reset_closed(self, ep_dir: str):
        env = judge_adapter.make_env()
        obs, info = env.reset(seed=2026, config={"mode": "closed", "episode_dir": ep_dir})
        return env, obs, info

    def test_C01_reset_returns_json_compatible_obs_info(self) -> None:
        _, obs, info = self._reset_closed(self.dir_c)
        self.assertIsInstance(obs, dict)
        self.assertIsInstance(info, dict)
        json.dumps(obs)
        json.dumps(info)

    def test_C02_first_obs_has_task_manifest_policy_budget_and_no_leaks(self) -> None:
        _, obs, info = self._reset_closed(self.dir_c)
        for key in ("task", "manifest", "policy", "remaining_steps"):
            self.assertIn(key, obs)
        self.assertIsInstance(obs["task"], str)
        self.assertEqual(obs["remaining_steps"], 100)
        blob = json.dumps({"obs": obs, "info": info})
        for forbidden in ("truth", "provenance", "master_seed", "sealed", self.dir_c):
            self.assertNotIn(forbidden, blob)

    def test_C03_manifest_fields_and_exact_counts(self) -> None:
        env, obs, _ = self._reset_closed(self.dir_c)
        m = obs["manifest"]
        for key in (
            "schema_version",
            "episode_id",
            "base_currency",
            "period_start",
            "period_end",
            "timezone",
            "record_counts",
            "document_count",
            "rounding_rules",
        ):
            self.assertIn(key, m)
        # Verify counts match actual paginated rows
        for tbl in ("ledger", "invoices", "payments", "fx"):
            seen = 0
            cursor = None
            while True:
                step_obs, _, _, _, _ = env.step(
                    {"name": "list_records", "args": {"table": tbl, "cursor": cursor, "limit": 50}}
                )
                seen += len(step_obs["result"]["records"])
                cursor = step_obs["result"]["next_cursor"]
                if cursor is None:
                    break
            self.assertEqual(seen, m["record_counts"][tbl], f"count mismatch on {tbl}")

    def test_C04_single_list_records_step_contract(self) -> None:
        env, _, _ = self._reset_closed(self.dir_c)
        obs, reward, terminated, truncated, info = env.step(
            {"name": "list_records", "args": {"table": "invoices", "cursor": None, "limit": 10}}
        )
        self.assertIs(type(terminated), bool)
        self.assertIs(type(truncated), bool)
        self.assertFalse(terminated)
        self.assertFalse(truncated)
        self.assertEqual(reward, 0)
        self.assertIsNone(obs["error"])
        self.assertEqual(obs["remaining_steps"], 99)
        json.dumps([obs, reward, terminated, truncated, info])

    def test_C05_pagination_over_large_fixture_L_three_pages(self) -> None:
        env, obs0, _ = self._reset_closed(self.dir_l)
        total_expected = obs0["manifest"]["record_counts"]["invoices"]
        self.assertGreaterEqual(total_expected, 101)
        pages = 0
        collected_ids: list[str] = []
        cursor = None
        while True:
            obs, _, _, _, _ = env.step(
                {"name": "list_records", "args": {"table": "invoices", "cursor": cursor, "limit": 50}}
            )
            self.assertIsNone(obs["error"])
            recs = obs["result"]["records"]
            self.assertLessEqual(len(recs), 50)
            collected_ids.extend(r["doc_id"] for r in recs)
            pages += 1
            cursor = obs["result"]["next_cursor"]
            if cursor is None:
                break
        self.assertGreaterEqual(pages, 3)
        self.assertEqual(len(collected_ids), total_expected)
        self.assertEqual(len(set(collected_ids)), total_expected)

    def test_C06_cursor_replay_same_page_same_order(self) -> None:
        env, _, _ = self._reset_closed(self.dir_l)
        obs1, _, _, _, _ = env.step(
            {"name": "list_records", "args": {"table": "invoices", "cursor": None, "limit": 50}}
        )
        c1 = obs1["result"]["next_cursor"]
        self.assertIsNotNone(c1)
        obs2a, _, _, _, _ = env.step(
            {"name": "list_records", "args": {"table": "invoices", "cursor": c1, "limit": 50}}
        )
        obs2b, _, _, _, _ = env.step(
            {"name": "list_records", "args": {"table": "invoices", "cursor": c1, "limit": 50}}
        )
        self.assertEqual(obs2a["result"]["records"], obs2b["result"]["records"])
        self.assertEqual(obs2a["result"]["next_cursor"], obs2b["result"]["next_cursor"])
        self.assertEqual(obs2a["remaining_steps"], obs2b["remaining_steps"] + 1)

    def test_C07_get_record_existing_R1(self) -> None:
        env, _, _ = self._reset_closed(self.dir_c)
        obs, _, _, _, _ = env.step(
            {"name": "get_record", "args": {"table": "invoices", "id": self.r1_id}}
        )
        self.assertIsNone(obs["error"])
        self.assertEqual(obs["result"]["doc_id"], self.r1_id)

    def test_C08_get_document_existing_D1_and_no_arbitrary_fs(self) -> None:
        env, _, _ = self._reset_closed(self.dir_c)
        obs, _, _, _, _ = env.step({"name": "get_document", "args": {"doc_id": self.d1_id}})
        self.assertIsNone(obs["error"])
        self.assertEqual(obs["result"]["doc_id"], self.d1_id)
        # Path traversal attempt must fail safely
        obs_bad, _, _, _, _ = env.step({"name": "get_document", "args": {"doc_id": "../sealed/truth.json"}})
        self.assertIsNotNone(obs_bad["error"])
        self.assertIsNone(obs_bad["result"])

    def test_C09_calculator_exact_decimal_0_1_plus_0_2(self) -> None:
        env, _, _ = self._reset_closed(self.dir_c)
        obs, _, _, _, _ = env.step({"name": "calculator", "args": {"expression": "0.1+0.2"}})
        self.assertIsNone(obs["error"])
        self.assertEqual(obs["result"], "0.3")

    def test_C10_calculator_rejects_non_arithmetic_code_or_file_access(self) -> None:
        env, _, _ = self._reset_closed(self.dir_c)
        for bad_expr in ("open('/etc/passwd').read()", "__import__('os').system('id')", "10**99999"):
            obs, _, _, _, _ = env.step({"name": "calculator", "args": {"expression": bad_expr}})
            self.assertIsNone(obs["result"])
            self.assertIsNotNone(obs["error"])

    def test_C11_get_record_missing_U_bounded_error_consumes_step(self) -> None:
        env, _, _ = self._reset_closed(self.dir_c)
        obs, _, terminated, truncated, _ = env.step(
            {"name": "get_record", "args": {"table": "invoices", "id": self.u_id}}
        )
        self.assertIsNone(obs["result"])
        self.assertIsNotNone(obs["error"])
        self.assertEqual(obs["remaining_steps"], 99)
        self.assertFalse(terminated)
        self.assertFalse(truncated)

    def test_C12_get_document_missing_U_bounded_error_consumes_step(self) -> None:
        env, _, _ = self._reset_closed(self.dir_c)
        obs, _, terminated, truncated, _ = env.step({"name": "get_document", "args": {"doc_id": self.u_id}})
        self.assertIsNone(obs["result"])
        self.assertIsNotNone(obs["error"])
        self.assertEqual(obs["remaining_steps"], 99)
        self.assertFalse(terminated)
        self.assertFalse(truncated)

    def test_C13_unknown_action_bounded_error_consumes_step(self) -> None:
        env, _, _ = self._reset_closed(self.dir_c)
        obs, _, terminated, truncated, _ = env.step({"name": "delete_database", "args": {}})
        self.assertIsNone(obs["result"])
        self.assertEqual(obs["error"]["code"], "UNKNOWN_ACTION")
        self.assertEqual(obs["remaining_steps"], 99)
        self.assertFalse(terminated)
        self.assertFalse(truncated)

    def test_C14_budget_decrements_after_valid_and_error_actions(self) -> None:
        env, _, _ = self._reset_closed(self.dir_c)
        obs1, _, _, _, _ = env.step({"name": "get_record", "args": {"table": "invoices", "id": self.r1_id}})
        obs2, _, _, _, _ = env.step({"name": "get_record", "args": {"table": "invoices", "id": self.u_id}})
        obs3, _, _, _, _ = env.step({"name": "get_record", "args": {"table": "invoices", "id": self.r1_id}})
        self.assertEqual(obs1["remaining_steps"], 99)
        self.assertEqual(obs2["remaining_steps"], 98)
        self.assertEqual(obs3["remaining_steps"], 97)
        self.assertEqual(obs3["result"]["doc_id"], self.r1_id)

    def test_C15_submit_terminates_and_freezes_findings(self) -> None:
        env, _, _ = self._reset_closed(self.dir_c)
        env.step({"name": "calculator", "args": {"expression": "1+1"}})
        obs, reward, terminated, truncated, _ = env.step(
            {"name": "submit", "args": {"findings": {"findings": []}}}
        )
        self.assertTrue(terminated)
        self.assertFalse(truncated)
        self.assertEqual(reward, 0)
        self.assertEqual(obs["result"], {"accepted": True})
        frozen_findings = env.final_findings
        frozen_steps = env.inspection_steps
        # Subsequent actions cannot mutate frozen result
        obs_after, _, term2, trunc2, _ = env.step(
            {"name": "submit", "args": {"findings": {"findings": [{"type": "FX_RATE_MISMATCH", "affected_ids": ["A"], "claimed_amount_minor": 1, "currency": "KZT", "evidence_ids": ["A"]}]}}}
        )
        self.assertTrue(term2)
        self.assertFalse(trunc2)
        self.assertIsNotNone(obs_after["error"])
        self.assertEqual(env.final_findings, frozen_findings)
        self.assertEqual(env.inspection_steps, frozen_steps)

    def test_C16_99_inspections_then_submit_on_step_100_accepted(self) -> None:
        env, _, _ = self._reset_closed(self.dir_c)
        for i in range(99):
            obs, _, terminated, truncated, _ = env.step({"name": "calculator", "args": {"expression": f"{i}+1"}})
            self.assertFalse(terminated)
            self.assertFalse(truncated)
            self.assertEqual(obs["remaining_steps"], 99 - i)
        obs100, reward, terminated, truncated, _ = env.step(
            {"name": "submit", "args": {"findings": {"findings": []}}}
        )
        self.assertTrue(terminated)
        self.assertFalse(truncated)
        self.assertEqual(obs100["result"], {"accepted": True})
        self.assertEqual(obs100["remaining_steps"], 0)
        self.assertEqual(env.inspection_steps, 99)
        self.assertEqual(reward, 0)

    def test_C17_100_inspections_without_submit_truncates_empty_findings(self) -> None:
        env, _, _ = self._reset_closed(self.dir_c)
        for i in range(99):
            _, _, terminated, truncated, _ = env.step({"name": "calculator", "args": {"expression": f"{i}+1"}})
            self.assertFalse(terminated)
            self.assertFalse(truncated)
        obs100, _, terminated, truncated, _ = env.step({"name": "calculator", "args": {"expression": "100+1"}})
        self.assertFalse(terminated)
        self.assertTrue(truncated)
        self.assertEqual(obs100["remaining_steps"], 0)
        self.assertEqual(env.final_findings, {"findings": []})
        # Late submit rejected and cannot modify empty findings
        obs_late, _, term_late, trunc_late, _ = env.step(
            {"name": "submit", "args": {"findings": {"findings": [{"type": "DUPLICATE_PAYMENT", "affected_ids": ["X"], "claimed_amount_minor": 100, "currency": "KZT", "evidence_ids": ["X"]}]}}}
        )
        self.assertFalse(term_late)
        self.assertTrue(trunc_late)
        self.assertIsNotNone(obs_late["error"])
        self.assertEqual(env.final_findings, {"findings": []})

    def test_C18_reproducible_60s_time_limit_truncates_empty_findings(self) -> None:
        fake_clock = _FakeClock(start=500.0)
        env = OfficialJudgeEnv(clock=fake_clock)
        env.reset(seed=2026, config={"mode": "closed", "episode_dir": self.dir_c})
        obs1, _, terminated, truncated, _ = env.step({"name": "calculator", "args": {"expression": "2+2"}})
        self.assertFalse(terminated)
        self.assertFalse(truncated)
        self.assertEqual(obs1["result"], "4")
        # Advance deterministic clock to exactly 60.0s
        fake_clock.advance(60.0)
        obs_to, reward, terminated, truncated, _ = env.step(
            {"name": "submit", "args": {"findings": {"findings": []}}}
        )
        self.assertFalse(terminated)
        self.assertTrue(truncated)
        self.assertEqual(reward, 0)
        self.assertEqual(obs_to["error"]["code"], "TIME_LIMIT")
        self.assertEqual(env.final_findings, {"findings": []})

    def test_C19_closed_vs_train_reward_separation_on_E(self) -> None:
        # Closed mode: reward MUST be numeric 0 on every step including terminal
        env_closed, _, _ = self._reset_closed(self.dir_e)
        _, r1, _, _, info1 = env_closed.step({"name": "list_records", "args": {"table": "invoices", "cursor": None, "limit": 5}})
        _, r2, term, _, info2 = env_closed.step({"name": "submit", "args": {"findings": {"findings": []}}})
        self.assertTrue(term)
        self.assertEqual(r1, 0)
        self.assertEqual(r2, 0)
        self.assertIs(type(r2), int)
        for forbidden_key in ("tp", "fp", "fn", "precision", "recall", "f1", "return", "truth"):
            self.assertNotIn(forbidden_key, info1)
            self.assertNotIn(forbidden_key, info2)

        # Judge still computes exact true score externally
        scored = judge_adapter.score_episode(self.dir_e, env_closed.final_findings, env_closed.inspection_steps)
        self.assertEqual(scored["fn"], 1)
        self.assertEqual(scored["return"], -1.0)

        # Train mode: terminal reward IS returned to policy
        env_train = judge_adapter.make_env()
        env_train.reset(seed=2026, config={"mode": "train", "episode_dir": self.dir_e})
        _, r_mid, _, _, _ = env_train.step({"name": "calculator", "args": {"expression": "1+1"}})
        self.assertEqual(r_mid, 0)
        _, r_term, term_t, _, _ = env_train.step({"name": "submit", "args": {"findings": {"findings": []}}})
        self.assertTrue(term_t)
        self.assertEqual(r_term, -1.0)

    def test_C20_no_leakage_across_all_records_docs_errors_and_process_isolation(self) -> None:
        for ep_dir in (self.dir_c, self.dir_e):
            env, obs0, info0 = self._reset_closed(ep_dir)
            collected: list[object] = [obs0, info0]
            for tbl in ("ledger", "invoices", "payments", "fx", "credit_notes", "bank_lines", "counterparties"):
                obs, _, _, _, info = env.step({"name": "list_records", "args": {"table": tbl, "cursor": None, "limit": 50}})
                collected.extend([obs, info])
            for err_action in (
                {"name": "get_record", "args": {"table": "invoices", "id": self.u_id}},
                {"name": "get_document", "args": {"doc_id": "../sealed/truth.json"}},
                {"name": "calculator", "args": {"expression": "open('manifest.json').read()"}},
                {"name": "unknown_cmd", "args": {}},
            ):
                obs, _, _, _, info = env.step(err_action)
                collected.extend([obs, info])
            blob = json.dumps(collected, ensure_ascii=False)
            for forbidden in ("truth.json", "provenance.json", "sealed/", "truth_commitment", ep_dir):
                self.assertNotIn(forbidden, blob)

        # Also verify true OS subprocess isolation runs cleanly without episode_dir access
        env_iso = judge_adapter.make_env()
        run = run_isolated_public_policy(
            env_iso,
            policy_name="random",
            episode_dir=self.dir_e,
            seed=7,
            mode="closed",
            score_fn=judge_adapter.score_episode,
        )
        self.assertTrue(run.terminated or run.truncated)
        self.assertIsNotNone(run.metrics)


if __name__ == "__main__":
    unittest.main()
