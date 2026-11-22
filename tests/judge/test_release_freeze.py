"""Contract-freeze tests (Phase 17, TZ section 24; D-17-01).

``tools/freeze_release.py`` pins the 30 frozen contract surfaces with
SHA-256. Until now the freeze was only ever checked by running the tool
by hand; a silent edit to a frozen file would therefore not fail any
test suite. These tests turn the freeze into a **gate**:

  * the committed manifest must match the working tree, byte for byte;
  * the frozen surface must be exactly the declared set (contracts, the
    operational configs, the rubric map, the Master TZ reference) and
    must never include the manifest itself;
  * the aggregate digest must stay the one the release was cut with, so
    a re-freeze cannot happen silently -- it needs a Change Request
    (AGENTS.md: frozen-contract changes require an approved CR).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools import freeze_release

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "configs" / "release_freeze.json"

#: The aggregate the published release was cut with (D-17-01 / D-12-02).
EXPECTED_AGGREGATE_PREFIX = "0747baf0"
EXPECTED_FROZEN_FILE_COUNT = 30


class TestContractFreezeManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_exists_and_is_self_describing(self) -> None:
        self.assertTrue(MANIFEST.is_file())
        self.assertEqual(self.manifest["schema_version"], "1.0.0")
        self.assertEqual(self.manifest["frozen_file_count"], len(self.manifest["files"]))

    def test_frozen_surface_is_the_declared_set(self) -> None:
        paths = [entry["path"] for entry in self.manifest["files"]]
        self.assertEqual(len(paths), EXPECTED_FROZEN_FILE_COUNT)
        self.assertNotIn("configs/release_freeze.json", paths)
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(
                    path.startswith("contracts/")
                    or path.startswith("configs/")
                    or path == "judge/rubric_map.json"
                    or path == "docs/reference/TwinLedger_v3_Master_TZ_AI_Agents.txt",
                    f"unexpected frozen surface: {path}",
                )

    def test_manifest_matches_the_working_tree(self) -> None:
        ok, errors = freeze_release.verify_freeze_manifest(MANIFEST)
        self.assertTrue(ok, errors)

    def test_aggregate_is_the_released_one(self) -> None:
        self.assertTrue(
            str(self.manifest["aggregate_sha256"]).startswith(EXPECTED_AGGREGATE_PREFIX),
            "the frozen aggregate changed; a re-freeze needs an approved CR",
        )

    def test_every_frozen_entry_records_size_and_digest(self) -> None:
        for entry in self.manifest["files"]:
            with self.subTest(path=entry["path"]):
                self.assertEqual(len(entry["sha256"]), 64)
                self.assertGreater(entry["bytes"], 0)
                self.assertTrue((REPO_ROOT / entry["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
