"""Environment configuration constants (A-004, A-006, A-007, A-008, A-011, A-013, A-015)."""

from __future__ import annotations

import unittest

from tests.support import CONFIGS, load_json


class LimitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.limits = load_json(CONFIGS / "environment" / "limits.json")
        cls.values = cls.limits["values"]

    def test_config_is_versioned_and_provisional(self) -> None:
        self.assertRegex(self.limits["config_version"], r"^\d+\.\d+\.\d+$")
        self.assertTrue(self.limits["provisional"])
        self.assertEqual(self.limits["status"], "provisional")
        self.assertTrue(self.limits["assumption_ids"])

    def test_all_required_constants_are_explicit(self) -> None:
        required = ["MAX_STEPS", "MAX_PAGE_SIZE", "MAX_FINDINGS", "MAX_EVIDENCE_IDS",
                    "MAX_REQUEST_BYTES", "MAX_CALC_EXPRESSION_LENGTH", "MAX_CALC_AST_NODES"]
        for key in required:
            self.assertIn(key, self.values, f"{key} must be explicit, never a hidden default")

    def test_values_are_sane(self) -> None:
        self.assertEqual(self.values["MAX_STEPS"], 100)
        self.assertEqual(self.values["MAX_PAGE_SIZE"], 50)
        self.assertGreaterEqual(self.values["MAX_FINDINGS"], 1)
        self.assertLessEqual(self.values["MAX_EVIDENCE_IDS"], 64)
        self.assertGreater(self.values["MAX_REQUEST_BYTES"], 1024)
        self.assertLessEqual(self.values["MAX_CALC_AST_NODES"], 256)
        self.assertGreater(self.values["WATCHDOG_SECONDS"], 0)

    def test_step_accounting(self) -> None:
        self.assertFalse(self.values["SUBMIT_COUNTS_AS_INSPECTION_STEP"])
        self.assertTrue(self.values["FAILED_CALL_COSTS_A_STEP"])

    def test_budget_semantics_are_deterministic(self) -> None:
        semantics = self.limits["semantics"]["budget"]
        self.assertIn("Deterministic", semantics)
        self.assertIn("watchdog", self.limits["semantics"]["budget"])

    def test_page_size_matches_the_contract(self) -> None:
        schema = load_json("contracts/tool_request.schema.json")
        limit_schema = None
        for variant in schema["oneOf"]:
            args = variant["properties"]["action"]["properties"]["args"]
            if "limit" in args.get("properties", {}):
                limit_schema = args["properties"]["limit"]
        self.assertIsNotNone(limit_schema, "list_records limit schema not found")
        self.assertEqual(limit_schema["maximum"], self.values["MAX_PAGE_SIZE"])

    def test_request_byte_limit_is_a_power_of_two_style_bounded_value(self) -> None:
        self.assertEqual(self.values["MAX_REQUEST_BYTES"], 65536)


class ModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mode = load_json(CONFIGS / "environment" / "mode.json")

    def test_closed_mode_is_the_default(self) -> None:
        self.assertEqual(self.mode["default_mode"], "CLOSED_EVAL")
        closed = self.mode["modes"]["CLOSED_EVAL"]
        self.assertFalse(closed["reward_visible_to_policy"])
        self.assertEqual(closed["step_reward_value"], 0)
        self.assertFalse(closed["diagnostics_visible_to_policy"])

    def test_info_allowlist_cannot_include_truth_fields(self) -> None:
        allowed = self.mode["modes"]["CLOSED_EVAL"]["info_fields_allowed"]
        for field in allowed:
            for token in ("truth", "seed", "label", "anomaly", "mutation", "score", "f1"):
                self.assertNotIn(token, field.lower(), f"info field {field!r} could leak {token}")
        self.assertEqual(allowed, ["steps_used", "steps_remaining"])

    def test_open_mode_is_explicitly_not_evidence_of_isolation(self) -> None:
        open_mode = self.mode["modes"]["OPEN_DEV"]
        self.assertIn("never evidence of isolation", open_mode["warning"])
        self.assertFalse(open_mode["used_by_make_verify"])
        self.assertTrue(self.mode["modes"]["CLOSED_EVAL"]["used_by_make_verify"])

    def test_forbidden_shortcuts_are_declared(self) -> None:
        forbidden = self.mode["forbidden"]
        self.assertTrue(forbidden["mode_from_environment_variable"])
        self.assertTrue(forbidden["reward_in_step_when_closed"])
        self.assertTrue(forbidden["truth_fields_in_info"])


class ResourceTests(unittest.TestCase):
    def test_runtime_constraints(self) -> None:
        resources = load_json(CONFIGS / "environment" / "resources.json")
        runtime = resources["runtime"]
        self.assertEqual(runtime["python"], "3.11")
        self.assertEqual(runtime["network"], "forbidden")
        self.assertEqual(runtime["cpu_cores"], 2)
        self.assertEqual(runtime["ram_mb"], 4096)
        self.assertLessEqual(runtime["disk_mb"], 1024)

    def test_targets_are_not_claims(self) -> None:
        resources = load_json(CONFIGS / "environment" / "resources.json")
        self.assertTrue(resources["measurement_policy"]["claim_only_measured_targets"])


class GeneratorConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.generator = load_json(CONFIGS / "generator" / "default.json")

    def test_seed_policy_forbids_public_seeds(self) -> None:
        policy = self.generator["master_seed_policy"]
        self.assertFalse(policy["seed_in_public_output"])
        self.assertIn("mutation/<operator>/<index>", policy["streams"])
        self.assertIn("sha256", policy["derivation"])

    def test_levels_are_ordered(self) -> None:
        levels = self.generator["levels"]
        for level in ("L1", "L2", "L3", "L4"):
            self.assertIn(level, levels)
            self.assertEqual(len(levels[level]["journal_entries"]), 2)
            self.assertLessEqual(levels[level]["journal_entries"][0], levels[level]["journal_entries"][1])
        self.assertLess(levels["L1"]["journal_entries"][0], levels["L2"]["journal_entries"][0])

    def test_synthetic_universe_rules(self) -> None:
        universe = self.generator["synthetic_universe"]
        for code in universe["jurisdiction_codes"]:
            self.assertRegex(code, r"^X[A-Z]$")
        self.assertTrue(universe["forbid_real_entity_names"])
        self.assertTrue(universe["forbid_personal_data"])

    def test_splits_never_tune_on_heldout(self) -> None:
        splits = self.generator["splits"]
        self.assertEqual(splits["heldout"], "never_used_for_tuning")
        self.assertEqual(splits["train"], "grouped_by_base_history")


if __name__ == "__main__":
    unittest.main()
