"""Integration tests: determinism, publish/verify round trip, public-only reads.

These tests treat the serializer as a black box and ask the questions an evaluation
harness would ask: does the same seed produce the same bytes, can a verifier rebuild
everything from ``public/`` alone, and does the public loader ever touch ``sealed/``?
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from contracts.canonical import canonical_json, sha256_hex
from contracts.errors import ContractError
from gen.build_episodes import build_episode
from gen.config import load_generator_config
from gen.serialize import (
    FORBIDDEN_PUBLIC_NAMES,
    read_public_episode,
    verify_written_episode,
    write_episode,
)


class SerializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_generator_config()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _episode(self, seed: str = "integration", difficulty: str = "L1"):
        return build_episode(
            master_seed=seed,
            config=self.config,
            difficulty=difficulty,
            created_at="2026-11-21T00:00:00+00:00",
        )

    # ------------------------------------------------------------- publishing
    def test_published_layout_is_public_and_sealed(self) -> None:
        written = write_episode(self._episode(), self.root)
        self.assertTrue(written.public_dir.is_dir())
        self.assertTrue(written.sealed_dir.is_dir())
        self.assertTrue(written.manifest_path.is_file())
        self.assertEqual(
            {path.name for path in written.sealed_dir.iterdir()},
            {"truth.json", "provenance.json", "verifier_crosscheck.json", "reject_log.json"},
        )

    def test_public_dir_holds_exactly_the_book_files(self) -> None:
        episode = self._episode()
        written = write_episode(episode, self.root)
        expected = {entry["name"] for entry in episode.manifest["public_files"]}
        actual = {path.name for path in written.public_dir.iterdir()}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 12)

    def test_public_file_hashes_match_the_manifest(self) -> None:
        episode = self._episode()
        written = write_episode(episode, self.root)
        for entry in episode.manifest["public_files"]:
            path = written.public_dir / entry["name"]
            payload = path.read_bytes()
            self.assertEqual(sha256_hex(payload), entry["sha256"], entry["name"])
            self.assertEqual(entry["bytes"], len(payload))

    def test_no_forbidden_name_in_public_dir(self) -> None:
        written = write_episode(self._episode(), self.root)
        for path in written.public_dir.iterdir():
            lowered = path.name.lower()
            for forbidden in FORBIDDEN_PUBLIC_NAMES:
                self.assertNotIn(forbidden, lowered, path.name)

    def test_rewriting_the_same_episode_is_idempotent(self) -> None:
        episode = self._episode()
        first = write_episode(episode, self.root)
        second = write_episode(self._episode(), self.root)
        self.assertEqual(first.public_digest, second.public_digest)
        self.assertEqual(dict(first.file_hashes), dict(second.file_hashes))

    def test_rewriting_a_different_package_is_refused(self) -> None:
        """A directory whose manifest digest differs must never be overwritten."""
        written = write_episode(self._episode("other-digest"), self.root)
        manifest = json.loads(written.manifest_path.read_text(encoding="utf-8"))
        manifest["public_digest"] = "0" * 64
        written.manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
        with self.assertRaises(ContractError):
            write_episode(self._episode("other-digest"), self.root)

    def test_verify_written_episode_passes(self) -> None:
        written = write_episode(self._episode(), self.root)
        report = verify_written_episode(written.root)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["public_file_count"], 12)
        self.assertEqual(report["stray_public_files"], [])

    def test_verify_detects_tampering(self) -> None:
        written = write_episode(self._episode(), self.root)
        target = written.public_dir / "payments.jsonl"
        original = target.read_text(encoding="utf-8")
        target.write_text(original + "{}\n", encoding="utf-8")
        report = verify_written_episode(written.root)
        self.assertFalse(report["ok"])
        self.assertIn("payments.jsonl", " ".join(report["digest_mismatches"]))

    def test_verify_detects_stray_public_file(self) -> None:
        written = write_episode(self._episode(), self.root)
        (written.public_dir / "leak.json").write_text("{}", encoding="utf-8")
        report = verify_written_episode(written.root)
        self.assertFalse(report["ok"])
        self.assertEqual(report["stray_public_files"], ["leak.json"])

    # ------------------------------------------------------------ public read
    def test_read_public_episode_returns_only_public_data(self) -> None:
        written = write_episode(self._episode(), self.root)
        payload = read_public_episode(written.root)
        self.assertEqual(set(payload), {"manifest", "files"})
        self.assertEqual(len(payload["files"]), 12)
        # Schema *names* are public contract metadata; the data itself must not leak.
        body = json.dumps(payload["files"], sort_keys=True).lower()
        for forbidden in (
            "affected_ids", "anomaly_type", "operator_id", "provenance",
            "expected_delta_minor", "side_effect_class", "distractor",
        ):
            self.assertNotIn(forbidden, body)
        manifest = dict(payload["manifest"])
        manifest.pop("schema_versions", None)
        for forbidden in ("anomaly_count", "finding_count", "operator_id", "distractor"):
            self.assertNotIn(forbidden, json.dumps(manifest, sort_keys=True).lower())

    def test_read_public_episode_fails_when_sealed_missing(self) -> None:
        written = write_episode(self._episode(), self.root)
        # A public-only reader must not need the sealed directory at all.
        for path in written.sealed_dir.iterdir():
            path.unlink()
        payload = read_public_episode(written.root)
        self.assertEqual(len(payload["files"]), 12)

    def test_read_public_episode_fails_when_public_missing(self) -> None:
        written = write_episode(self._episode(), self.root)
        for path in written.public_dir.iterdir():
            path.unlink()
        with self.assertRaises(ContractError):
            read_public_episode(written.root)

    def test_manifest_digest_matches_public_digest(self) -> None:
        written = write_episode(self._episode(), self.root)
        manifest = json.loads(written.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["public_digest"], written.public_digest)

    # ------------------------------------------------------------ determinism
    def test_two_seeds_differ(self) -> None:
        first = write_episode(self._episode("integration-a"), self.root)
        second = write_episode(self._episode("integration-b"), self.root)
        self.assertNotEqual(first.public_digest, second.public_digest)
        self.assertNotEqual(first.file_hashes["payments.jsonl"], second.file_hashes["payments.jsonl"])

    def test_same_seed_same_bytes_across_processes(self) -> None:
        """Determinism must not depend on in-process state (no PYTHONHASHSEED leak)."""
        script = (
            "import json,sys;"
            "from gen.config import load_generator_config;"
            "from gen.build_episodes import build_episode;"
            "e=build_episode(master_seed='process', config=load_generator_config(), difficulty='L1',"
            " created_at='2026-11-21T00:00:00+00:00');"
            "print(e.manifest['public_digest']);"
            "print(json.dumps(e.truth, sort_keys=True))"
        )
        import subprocess
        import sys

        digests = []
        for hash_seed in ("0", "12345"):
            env = {"PYTHONHASHSEED": hash_seed, "PATH": "/usr/bin:/bin"}
            output = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                check=True,
                cwd=str(Path(__file__).resolve().parents[2]),
                env=env,
            )
            digests.append(output.stdout.strip().splitlines())
        self.assertEqual(digests[0], digests[1])

    def test_episode_json_is_canonical(self) -> None:
        written = write_episode(self._episode(), self.root)
        manifest = json.loads(written.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(written.manifest_path.read_text(encoding="utf-8"), canonical_json(manifest) + "\n")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
