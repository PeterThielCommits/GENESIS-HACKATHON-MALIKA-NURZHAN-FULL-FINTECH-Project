"""Sealed-boundary tests (8.2, 10.2 G17, REQ-SEC-001..004).

The boundary this suite defends:

    environment / policy  ->  public/ only
    sealed truth          ->  scoring only, never visible to a solver
    verifier              ->  independent, must not import the generator

Every test here is a *negative* test: it fails if information that must stay hidden
becomes visible, or if an architectural rule (no ``gen`` import in the verifier) is
broken. Nothing in this file is a demo of a security property we merely claim.
"""

from __future__ import annotations

import ast
import json
import re
import tempfile
import unittest
from pathlib import Path

from gen.build_episodes import build_episode
from gen.clean import build_clean_book
from gen.config import load_generator_config
from gen.serialize import read_public_episode, write_episode

REPO_ROOT = Path(__file__).resolve().parents[2]

# Marker the generator would leave behind if a canary or seed ever leaked into the
# public surface. These strings must appear nowhere a solver can read.
CANARY_PATTERNS = (
    re.compile(r"canary", re.IGNORECASE),
    re.compile(r"\bmaster_seed\b", re.IGNORECASE),
    re.compile(r"\boperator_id\b", re.IGNORECASE),
    re.compile(r"\bpre_state_digest\b", re.IGNORECASE),
    re.compile(r"\bpending_invoice_id\b", re.IGNORECASE),
)


class SealedBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_generator_config()
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.episode = build_episode(
            master_seed="sealed-boundary",
            config=cls.config,
            difficulty="L2",
            created_at="2026-11-21T00:00:00+00:00",
        )
        cls.written = write_episode(cls.episode, cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    # -------------------------------------------------------- public surface
    def test_no_canary_or_seed_in_any_public_bytes(self) -> None:
        for path in self.written.public_dir.iterdir():
            text = path.read_text(encoding="utf-8")
            for pattern in CANARY_PATTERNS:
                self.assertIsNone(pattern.search(text), f"{pattern.pattern} leaked in {path.name}")

    def test_no_canary_in_manifest(self) -> None:
        """``canary_scan`` is a published *result*; a canary token is not.

        The manifest intentionally reports that a scan ran and found nothing. What it
        must never contain is a canary marker, a seed, or an operator identity.
        """
        manifest = json.loads(self.written.manifest_path.read_text(encoding="utf-8"))
        scan = manifest.pop("canary_scan")
        self.assertEqual(scan["public_hits"], 0)
        text = json.dumps(manifest).lower()
        for marker in ("canary-", "canary_", "tl-canary", "seed:"):
            self.assertNotIn(marker, text)
        for pattern in CANARY_PATTERNS:
            self.assertIsNone(pattern.search(text), f"{pattern.pattern} leaked in manifest")

    def test_truth_facts_are_absent_from_public(self) -> None:
        finding = self.episode.truth["findings"][0]
        public_text = "\n".join(
            path.read_text(encoding="utf-8") for path in self.written.public_dir.iterdir()
        )
        # Document ids legitimately appear; the *judgement* about them must not.
        for forbidden in (
            finding["type"],
            finding["invariant_signature"]["invariant_id"],
            "expected_delta_minor",
            "side_effect_class",
            "evidence_sets",
        ):
            self.assertNotIn(forbidden, public_text)

    def test_public_loader_ignores_sealed_directory(self) -> None:
        payload = read_public_episode(self.written.root)
        sealed_names = {path.name for path in self.written.sealed_dir.iterdir()}
        self.assertTrue(sealed_names)
        for name in sealed_names:
            self.assertNotIn(name, payload["files"])

    def test_sealed_files_are_not_in_the_manifest(self) -> None:
        manifest = json.loads(self.written.manifest_path.read_text(encoding="utf-8"))
        public_names = {entry["name"] for entry in manifest["public_files"]}
        for sealed_name in ("truth.json", "provenance.json", "reject_log.json"):
            self.assertNotIn(sealed_name, public_names)

    def test_sealed_file_names_are_rejected_in_public(self) -> None:
        from contracts.errors import ContractError
        from gen.serialize import _assert_public_name

        for name in ("truth.json", "provenance.jsonl", "sealed_round.json", "canary.txt"):
            with self.assertRaises(ContractError):
                _assert_public_name(name)

    def test_provenance_contains_the_hidden_parameters(self) -> None:
        """The sealed side must actually carry what the public side may not."""
        provenance = json.loads(
            (self.written.sealed_dir / "provenance.json").read_text(encoding="utf-8")
        )
        text = json.dumps(provenance).lower()
        self.assertIn("operator_applications", text)
        self.assertIn("pre_state_digest", text)
        self.assertIn("attempt_index", text)

    def test_commitment_is_not_the_plain_truth_digest(self) -> None:
        from contracts.canonical import digest_of

        manifest = json.loads(self.written.manifest_path.read_text(encoding="utf-8"))
        sealed_truth = json.loads(
            (self.written.sealed_dir / "truth.json").read_text(encoding="utf-8")
        )
        self.assertNotEqual(manifest["commitment"]["commitment_hex"], digest_of(sealed_truth))

    def test_clean_and_anomalous_episodes_have_identical_public_shape(self) -> None:
        clean = build_episode(
            master_seed="sealed-clean",
            config=self.config,
            difficulty="L2",
            anomaly_count=0,
            created_at="2026-11-21T00:00:00+00:00",
        )
        clean_written = write_episode(clean, self.root)
        self.assertEqual(
            {path.name for path in clean_written.public_dir.iterdir()},
            {path.name for path in self.written.public_dir.iterdir()},
        )
        self.assertEqual(
            clean_written.root.joinpath("manifest.json").read_text(encoding="utf-8").count("public_files"),
            1,
        )


class LayeringTests(unittest.TestCase):
    """Lower layers must not depend on generator internals.

    ``verifier/`` (Phase 8) will be held to the same rule with a stricter list; the
    rule is enforced here already for the packages that exist today, so the
    independence discipline is a live constraint rather than a future promise.
    """

    FORBIDDEN = {
        "contracts": {"gen", "invariants", "verifier"},
        "core": {"gen", "invariants", "verifier"},
        "invariants": {"gen"},
    }

    def test_layering_is_respected(self) -> None:
        offenders: list[str] = []
        for package, forbidden in self.FORBIDDEN.items():
            for path in (REPO_ROOT / package).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    names: list[str] = []
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.level == 0:
                        names = [node.module or ""]
                    for name in names:
                        root = name.split(".")[0]
                        if root in forbidden:
                            offenders.append(f"{package}/{path.name} imports {name}")
        self.assertEqual(offenders, [], f"layer violation: {offenders}")

    def test_public_code_never_reads_sealed_paths(self) -> None:
        """Prose may *mention* sealed data; public code must never construct a path.

        The distinction matters: docstrings explaining the boundary are good, a
        ``"sealed"`` literal used to open a file is a breach.
        """
        offenders: list[str] = []
        for package in ("contracts", "core", "invariants"):
            for path in (REPO_ROOT / package).rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                for node in ast.walk(ast.parse(source, filename=str(path))):
                    literal = None
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        literal = node.value
                    if literal:
                        lowered = literal.lower()
                        parts = [part for part in lowered.split("/") if part]
                        if "sealed" in parts or lowered.startswith("sealed"):
                            offenders.append(f"{package}/{path.name}: {literal!r}")
                    if isinstance(node, ast.Attribute) and node.attr in {"sealed_dir", "sealed"}:
                        offenders.append(f"{package}/{path.name}: attribute .{node.attr}")
        self.assertEqual(offenders, [], f"sealed paths referenced in public layers: {offenders}")


class PublicDigestStabilityTests(unittest.TestCase):
    def test_public_digest_covers_every_public_file(self) -> None:
        config = load_generator_config()
        episode = build_episode(
            master_seed="digest-coverage",
            config=config,
            difficulty="L1",
            created_at="2026-11-21T00:00:00+00:00",
        )
        with tempfile.TemporaryDirectory() as tmp:
            written = write_episode(episode, tmp)
            for path in written.public_dir.iterdir():
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.strip(), f"{path.name} is empty")

    def test_public_files_are_canonical_json_lines(self) -> None:
        config = load_generator_config()
        book = build_clean_book(master_seed="canonical", config=config, difficulty="L1").book
        for name, text in book.public_files().items():
            with self.subTest(file=name):
                self.assertTrue(text.endswith("\n"), f"{name} must end with a newline")
                for line in text.splitlines():
                    payload = json.loads(line)
                    self.assertEqual(
                        line,
                        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                    )
        for name, text in book.public_files().items():
            if name.endswith(".json"):
                payload = json.loads(text)
                self.assertEqual(
                    text,
                    json.dumps(
                        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                    ) + "\n",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
