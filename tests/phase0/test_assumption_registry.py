"""Phase 0 gate: every assumption is registered, isolated and consistent with configs."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.support import CONFIGS, DOCS, ROOT, assumptions, load_json, read_text


class AssumptionRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_json(DOCS / "ASSUMPTIONS.json")
        cls.items = assumptions()

    def test_all_sixteen_assumptions_are_registered_exactly_once(self) -> None:
        expected = [f"A-{n:03d}" for n in range(1, 17)]
        self.assertEqual(sorted(self.items), expected)

    def test_status_vocabulary_and_reasoning(self) -> None:
        self.assertEqual(self.registry["status_vocabulary"], ["UNRESOLVED", "CONFIRMED", "MODIFIED"])
        for aid, item in self.items.items():
            self.assertIn(item["status"], self.registry["status_vocabulary"], aid)
            self.assertTrue(item["status_reason"], aid)
            if item["status"] == "CONFIRMED":
                self.assertTrue(item["official_source"], f"{aid} claims CONFIRMED with no official source")
                self.assertTrue((ROOT / item["official_source"]).exists(), aid)

    def test_no_assumption_is_silently_confirmed(self) -> None:
        confirmed = [aid for aid, item in self.items.items() if item["status"] == "CONFIRMED"]
        self.assertEqual(
            confirmed, [],
            "Phase 0 archived no organizer document, so no assumption may be CONFIRMED (D-0001)",
        )

    def test_every_assumption_names_existing_isolation_points(self) -> None:
        for aid, item in self.items.items():
            self.assertTrue(item["isolation_points"], aid)
            for point in item["isolation_points"]:
                self.assertTrue((ROOT / point).exists(), f"{aid}: isolation point missing: {point}")

    def test_isolation_points_are_configs_or_adapter_for_external_unknowns(self) -> None:
        # External-facing unknowns must be isolated in adapter/ or configs/, never in core logic.
        for aid, item in self.items.items():
            points = item["isolation_points"]
            self.assertTrue(
                any(p.startswith(("adapter/", "configs/", "contracts/", "spec/")) or p in {".gitignore", "pyproject.toml"}
                    for p in points),
                f"{aid} is not isolated in an external boundary: {points}",
            )

    def test_questions_and_decisions_exist(self) -> None:
        questions = read_text(DOCS / "QUESTIONS.md")
        decisions = read_text(DOCS / "DECISIONS.md")
        for aid, item in self.items.items():
            self.assertIn(f"## {item['question_id']} ", questions, f"{aid} question missing")
            for decision in item["decision_ids"]:
                self.assertIn(f"## {decision} ", decisions, f"{aid} decision missing: {decision}")

    def test_verification_test_exists(self) -> None:
        for aid, item in self.items.items():
            test_file = item["verification_test"].split("::")[0]
            self.assertTrue((ROOT / test_file).is_file(), f"{aid}: {test_file} does not exist")

    def test_required_fields_are_present(self) -> None:
        for aid, item in self.items.items():
            for key in ("title_ru", "title_en", "spec_ref", "provisional_value", "close_condition",
                        "owner", "impact_if_wrong", "notes"):
                self.assertIn(key, item, f"{aid} lacks {key}")

    # ---- cross-checks: the isolated value really is the configured value -----------------
    def test_A004_limits_match_configuration(self) -> None:
        limits = load_json(CONFIGS / "environment" / "limits.json")["values"]
        value = self.items["A-004"]["provisional_value"]
        self.assertEqual(value["MAX_STEPS"], limits["MAX_STEPS"])
        self.assertEqual(value["MAX_PAGE_SIZE"], limits["MAX_PAGE_SIZE"])

    def test_A005_reward_matches_configuration(self) -> None:
        reward = load_json(CONFIGS / "scoring" / "reward.json")
        value = self.items["A-005"]["provisional_value"]
        self.assertEqual(str(reward["parameters"]["ETA"]), value["ETA"])
        self.assertEqual(reward["parameters"]["max_steps"], value["max_steps"])
        self.assertEqual(reward["formula"], value["formula"])

    def test_A006_submit_accounting_matches_configuration(self) -> None:
        limits = load_json(CONFIGS / "environment" / "limits.json")["values"]
        value = self.items["A-006"]["provisional_value"]
        self.assertEqual(value["SUBMIT_COUNTS_AS_INSPECTION_STEP"], limits["SUBMIT_COUNTS_AS_INSPECTION_STEP"])
        self.assertEqual(value["FAILED_CALL_COSTS_A_STEP"], limits["FAILED_CALL_COSTS_A_STEP"])

    def test_A008_mode_matches_configuration(self) -> None:
        mode = load_json(CONFIGS / "environment" / "mode.json")
        value = self.items["A-008"]["provisional_value"]
        self.assertEqual(value["default_mode"], mode["default_mode"])
        self.assertEqual(mode["modes"][value["default_mode"]]["step_reward_value"],
                         value["step_reward"])
        self.assertFalse(mode["modes"]["CLOSED_EVAL"]["reward_visible_to_policy"])

    def test_A009_cursor_matches_configuration(self) -> None:
        cursor = load_json(CONFIGS / "environment" / "cursor.json")
        value = self.items["A-009"]["provisional_value"]
        self.assertEqual(value["format"], cursor["token"]["format"])
        self.assertEqual(value["authenticated"], cursor["token"]["authenticated"])
        self.assertEqual(value["bound_fields"], cursor["token"]["payload_fields"])

    def test_A011_watchdog_matches_configuration(self) -> None:
        limits = load_json(CONFIGS / "environment" / "limits.json")["values"]
        self.assertEqual(self.items["A-011"]["provisional_value"]["WATCHDOG_SECONDS"],
                         limits["WATCHDOG_SECONDS"])

    def test_A013_runtime_matches_configuration(self) -> None:
        resources = load_json(CONFIGS / "environment" / "resources.json")["runtime"]
        value = self.items["A-013"]["provisional_value"]
        self.assertEqual(value["python"], resources["python"])
        self.assertEqual(value["network"], resources["network"])
        self.assertEqual(value["cpu_cores"], resources["cpu_cores"])
        self.assertEqual(value["ram_mb"], resources["ram_mb"])

    def test_A014_tolerance_matches_configuration(self) -> None:
        tolerance = load_json(CONFIGS / "scoring" / "tolerance.json")
        value = self.items["A-014"]["provisional_value"]
        self.assertEqual(value["rule_id"], tolerance["rule_id"])
        self.assertEqual(value["formula"], tolerance["formula"])

    def test_A016_rubric_matches_configuration_and_map(self) -> None:
        rubric_config = load_json(CONFIGS / "rubric" / "provisional.json")
        rubric_map = load_json("judge/rubric_map.json")
        value = self.items["A-016"]["provisional_value"]
        scored = [b for b in rubric_config["blocks"] if b["block"] != "engineering"]
        self.assertEqual(len(scored), value["blocks"], "four scored blocks plus engineering criteria")
        self.assertTrue(any(b["block"] == "engineering" for b in rubric_config["blocks"]))
        self.assertEqual(sum(b["provisional_points"] for b in rubric_config["blocks"]), value["total_points"])
        self.assertFalse(rubric_map["official_rubric_available"])
        self.assertFalse(rubric_config["official_rubric_available"])

    def test_A002_types_match_catalog_and_schema(self) -> None:
        value = self.items["A-002"]["provisional_value"]
        catalog = [item["type"] for item in load_json("spec/anomaly_catalog.json")["types"]]
        schema = load_json("contracts/common.defs.json")["$defs"]["anomaly_type"]["enum"]
        self.assertEqual(sorted(value["types"]), sorted(catalog))
        self.assertEqual(sorted(value["types"]), sorted(schema))

    def test_A003_finding_fields_match_schema(self) -> None:
        value = self.items["A-003"]["provisional_value"]
        finding = load_json("contracts/finding.schema.json")
        self.assertEqual(sorted(finding["required"]), sorted(value["required"]))
        for optional in value["optional"]:
            self.assertIn(optional, finding["properties"])

    def test_A015_seed_never_public(self) -> None:
        generator = load_json(CONFIGS / "generator" / "default.json")
        mode = load_json(CONFIGS / "environment" / "mode.json")
        self.assertFalse(generator["master_seed_policy"]["seed_in_public_output"])
        allowed = mode["modes"]["CLOSED_EVAL"]["info_fields_allowed"]
        self.assertEqual(allowed, ["steps_used", "steps_remaining"])
        for token in ("seed", "truth", "mutation"):
            self.assertFalse(any(token in field for field in allowed), token)

    def test_registry_source_is_archived(self) -> None:
        source = self.registry["source"].split(" ")[0]
        self.assertTrue((ROOT / source).is_file(), f"registry cites a missing source: {source}")


if __name__ == "__main__":
    unittest.main()
