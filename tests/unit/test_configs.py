"""Config validation tests (REQ-CONTRACT-020..022)."""

import json
import unittest
from pathlib import Path

from contracts.canonical import config_hash
from contracts.loader import validate_instance

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIGS = [
    "configs/generator/default.json",
    "configs/environment/default.json",
    "configs/scoring/default.json",
    "configs/arena/default.json",
    "configs/rubric/default.json",
]


class TestConfigs(unittest.TestCase):
    def test_all_configs_have_version(self):
        for rel in CONFIGS:
            data = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            self.assertEqual(validate_instance("config", data), [], rel)
            self.assertIn("config_version", data)
            self.assertEqual(data.get("config_hash"), config_hash(data), rel)

    def test_config_hash_deterministic(self):
        data = json.loads((ROOT / "configs/environment/default.json").read_text(encoding="utf-8"))
        self.assertEqual(config_hash(data), config_hash(dict(data)))
        self.assertEqual(len(config_hash(data)), 64)

    def test_environment_budget_bounds(self):
        data = json.loads((ROOT / "configs/environment/default.json").read_text(encoding="utf-8"))
        self.assertLessEqual(data["max_page_size"], 50)
        self.assertGreaterEqual(data["max_steps"], 1)
        self.assertIn(data["mode"], ("CLOSED_EVAL", "OPEN_DEV"))


if __name__ == "__main__":
    unittest.main()
