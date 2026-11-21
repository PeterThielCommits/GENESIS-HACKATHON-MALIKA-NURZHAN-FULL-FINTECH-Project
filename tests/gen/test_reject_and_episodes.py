"""Rejection sampling and full-episode tests (Phase 4.7 + integration gates).

Covers REQ-GEN-020..022 (bounded attempts, observable rates, determinism) and the
Phase 4 EXIT GATE: two anomaly types generate and pass every quality gate.
"""

from __future__ import annotations

import unittest

from contracts.canonical import digest_of
from contracts.errors import ConfigError, OperatorError, RejectBudgetExhausted, RejectError
from gen.build_episodes import build_episode, build_episode_set
from gen.config import load_generator_config
from gen.reject import REJECT_REASONS, RejectLog, Rejected, assert_distinct_affected_ids, reject, sample


class SampleTests(unittest.TestCase):
    def test_returns_first_success(self) -> None:
        log = RejectLog()
        value = sample(attempt=lambda index: "ok" if index >= 2 else reject("NO_CANDIDATE_PARAMS"),
                       limit=5, log=log)
        self.assertEqual(value, "ok")
        self.assertEqual(log.attempts, 2)
        self.assertTrue(log.accepted)

    def test_budget_exhausted_raises(self) -> None:
        log = RejectLog()
        with self.assertRaises(RejectBudgetExhausted):
            sample(attempt=lambda index: reject("SIGNATURE_MISMATCH"), limit=3, log=log)
        self.assertEqual(log.attempts, 3)
        self.assertFalse(log.accepted)

    def test_invalid_limit_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            sample(attempt=lambda index: 1, limit=0, log=RejectLog())

    def test_unknown_reason_code_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            RejectLog().record("MADE_UP_REASON")
        with self.assertRaises(ConfigError):
            reject("NOT_A_CODE")

    def test_reason_codes_are_frozen(self) -> None:
        self.assertIn("CLEAN_TWIN_INVARIANT_VIOLATION", REJECT_REASONS)
        self.assertIn("SIGNATURE_MISMATCH", REJECT_REASONS)
        self.assertIn("AMBIGUOUS_FINDINGS", REJECT_REASONS)

    def test_distinct_affected_ids_gate(self) -> None:
        assert_distinct_affected_ids(
            [{"affected_ids": ["PAY-1", "JE-1"]}, {"affected_ids": ["PAY-2"]}]
        )
        with self.assertRaises(Rejected):
            assert_distinct_affected_ids(
                [{"affected_ids": ["PAY-1"]}, {"affected_ids": ["PAY-1"]}]
            )

    def test_stats_shape(self) -> None:
        log = RejectLog()
        log.record("NO_CANDIDATE_PARAMS")
        log.record("NO_CANDIDATE_PARAMS")
        stats = log.to_stats()
        self.assertEqual(stats["attempts"], 2)
        self.assertEqual(stats["by_reason"], {"NO_CANDIDATE_PARAMS": 2})
        self.assertFalse(stats["accepted"])


class EpisodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_generator_config()

    def test_clean_episode_has_no_findings(self) -> None:
        episode = build_episode(
            master_seed="ep-clean", config=self.config, difficulty="L1", anomaly_count=0,
            created_at="2026-11-21T00:00:00+00:00",
        )
        self.assertEqual(episode.mode, "CLEAN")
        self.assertEqual(episode.truth["findings"], [])
        self.assertEqual(episode.truth["mode"], "CLEAN")
        self.assertEqual(episode.diff.summary()["added"], 0)

    def test_anomalous_episode_has_diff_backed_findings(self) -> None:
        episode = build_episode(
            master_seed="ep-anom", config=self.config, difficulty="L1",
            created_at="2026-11-21T00:00:00+00:00",
        )
        self.assertEqual(episode.mode, "ANOMALOUS")
        self.assertEqual(len(episode.findings), 1)
        finding = episode.truth["findings"][0]
        self.assertGreater(finding["amount_minor"], 0)
        self.assertTrue(finding["evidence_sets"])
        self.assertTrue(finding["affected_ids"])
        self.assertFalse(episode.diff.is_empty())
        self.assertTrue(episode.diff.added() or episode.diff.modified())

    def test_manifest_hides_private_facts(self) -> None:
        episode = build_episode(
            master_seed="ep-anom", config=self.config, difficulty="L1",
            created_at="2026-11-21T00:00:00+00:00",
        )
        payload = dict(episode.manifest)
        # Schema *names* are public contract metadata; the check targets leaked facts.
        payload.pop("schema_versions", None)
        # The commitment *algorithm label* documents the hash construction; it is
        # contract text, not a leaked digest. Inspect all other manifest content.
        commitment = dict(payload.pop("commitment"))
        self.assertEqual(commitment["algorithm"], "sha256(salt||truth_digest)")
        text = str(payload).lower()
        for forbidden in (
            "finding_count", "anomaly_count", "operator_id", "duplicate_payment",
            "partial_payment", "affected_ids", "provenance", "master_seed",
            "distractor", "subtype",
        ):
            self.assertNotIn(forbidden, text)

    def test_commitment_is_deterministic_and_salted(self) -> None:
        first = build_episode(
            master_seed="ep-anom", config=self.config, difficulty="L1",
            created_at="2026-11-21T00:00:00+00:00",
        )
        second = build_episode(
            master_seed="ep-anom", config=self.config, difficulty="L1",
            created_at="2026-11-21T00:00:00+00:00",
        )
        self.assertEqual(
            first.manifest["commitment"]["commitment_hex"],
            second.manifest["commitment"]["commitment_hex"],
        )
        self.assertNotEqual(
            first.manifest["commitment"]["commitment_hex"],
            digest_of(first.truth),
            "commitment must not equal the plain truth digest",
        )

    def test_episode_is_deterministic(self) -> None:
        first = build_episode(
            master_seed="ep-det", config=self.config, difficulty="L2",
            created_at="2026-11-21T00:00:00+00:00",
        )
        second = build_episode(
            master_seed="ep-det", config=self.config, difficulty="L2",
            created_at="2026-11-21T00:00:00+00:00",
        )
        self.assertEqual(first.public_files, second.public_files)
        self.assertEqual(first.truth, second.truth)
        self.assertEqual(first.manifest["public_digest"], second.manifest["public_digest"])

    def test_two_anomaly_types_generate(self) -> None:
        """EXIT GATE 4: both anomaly families generate from ordinary seeds.

        Rejection is a documented, expected outcome of bounded sampling, so a seed
        that exhausts its budget is counted, not treated as a silent failure.
        """
        seen: set[str] = set()
        published = 0
        rejected = 0
        for index in range(24):
            try:
                episode = build_episode(
                    master_seed=f"ep-types-{index}", config=self.config, difficulty="L2",
                    created_at="2026-11-21T00:00:00+00:00",
                )
            except RejectBudgetExhausted:
                rejected += 1
                continue
            published += 1
            seen.update(finding.anomaly_type for finding in episode.findings)
        self.assertEqual(seen, {"DUPLICATE_PAYMENT", "PARTIAL_PAYMENT_ALLOCATION"})
        self.assertGreaterEqual(published, 12, f"only {published} episodes published")
        self.assertLess(rejected, published, "rejection rate must stay a minority")

    def test_budget_bounds_are_enforced(self) -> None:
        """Two distinct bounded failures: config limit and sampling budget."""
        with self.assertRaises(ConfigError):
            build_episode(master_seed="ep-too-many", config=self.config, difficulty="L1",
                          anomaly_count=99)  # exceeds the configured maximum
        log = RejectLog()
        with self.assertRaises(RejectBudgetExhausted) as context:
            sample(attempt=lambda index: reject("SIGNATURE_MISMATCH"), limit=2, log=log)
        self.assertEqual(context.exception.context["attempts"], 2)

    def test_reject_stats_recorded(self) -> None:
        episode = build_episode(
            master_seed="ep-stats", config=self.config, difficulty="L1",
            created_at="2026-11-21T00:00:00+00:00",
        )
        stats = episode.reject_stats
        self.assertIn("attempts", stats)
        self.assertTrue(stats["accepted"])
        self.assertIsInstance(stats["by_reason"], dict)

    def test_same_seed_same_reject_behaviour(self) -> None:
        episodes, failures = build_episode_set(
            seeds=[f"determinism-{index}" for index in range(4)],
            config=self.config,
            difficulty="L1",
        )
        repeats, repeat_failures = build_episode_set(
            seeds=[f"determinism-{index}" for index in range(4)],
            config=self.config,
            difficulty="L1",
        )
        self.assertEqual(
            [(e.mode, len(e.findings), e.manifest["public_digest"]) for e in episodes],
            [(e.mode, len(e.findings), e.manifest["public_digest"]) for e in repeats],
        )
        self.assertEqual(
            [f.get("attempts") for f in failures],
            [f.get("attempts") for f in repeat_failures],
        )

    def test_distractors_present_with_public_evidence(self) -> None:
        episode = build_episode(
            master_seed="ep-distr", config=self.config, difficulty="L2",
            created_at="2026-11-21T00:00:00+00:00",
        )
        for entry in episode.truth["distractors"]:
            self.assertTrue(entry["public_evidence_ids"])
            self.assertGreaterEqual(len(entry["distinguishing_fact"]), 8)

    def test_provenance_lists_operator_applications(self) -> None:
        episode = build_episode(
            master_seed="ep-prov", config=self.config, difficulty="L1",
            created_at="2026-11-21T00:00:00+00:00",
        )
        applications = episode.provenance["operator_applications"]
        self.assertEqual(len(applications), 1)
        self.assertIn("pre_state_digest", applications[0])
        self.assertIn("post_state_digest", applications[0])
        self.assertEqual(applications[0]["status"], "APPLIED")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
