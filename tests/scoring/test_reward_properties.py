"""Five mandatory reward-property suites (Phase 6 task 6.6, TZ 15.7).

P1..P5 are evaluated over a representative corpus (all four anomaly
types plus clean episodes), never on a single hand-picked example. The
automatic results table is written to
``artifacts/reports/latest/reward_property_matrix.json`` and includes
the machine verdict of every property.
"""

from __future__ import annotations

import json
import platform
import sys
import unittest
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from contracts.canonical import canonical_json, sha256_hex
from scoring.diagnostics import build_reward_property_matrix, evaluate_reward_properties
from scoring.official_scorer import OFFICIAL_STEP_PENALTY_WEIGHT
from scoring.reward import compute_reward, load_scoring_config
from tests.scoring import fixtures as fx

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / "artifacts" / "reports" / "latest" / "reward_property_matrix.json"

BASELINE_STEPS = 20
P5_STEP_SWEEP = (0, 25, 50, 75, 100)


def build_corpus():
    """Hand-authored representative scenarios (clean + one per type)."""
    return [
        ("clean-1", "clean", None, []),
        ("clean-2", "clean", None, []),
        ("dup-1", "dirty", "DUPLICATE_PAYMENT", [fx.duplicate_payment_truth("T-DUP")]),
        ("part-1", "dirty", "PARTIAL_PAYMENT_ALLOCATION", [fx.partial_alloc_truth("T-PART")]),
        ("fx-1", "dirty", "FX_RATE_MISMATCH", [fx.fx_truth("T-FX")]),
        ("cut-1", "dirty", "PERIOD_CUTOFF", [fx.cutoff_truth("T-CUT")]),
    ]


def submissions_for(kind: str, truths):
    """Strategy -> findings mapping for one scenario."""
    honest = [fx.honest_finding(t) for t in truths]
    noise = fx.finding(
        anomaly_type="DUPLICATE_PAYMENT",
        affected_ids=("PAY:999",),
        claimed_amount=111,
        evidence_ids=("JE:999",),
    )
    strategies = {
        "honest": honest,
        "silence": [],
        "false_accusation": [noise],
        "duplicate_spam": honest + honest + honest,
        "flag_all": fx.flag_all_findings(),
    }
    if kind == "dirty":
        strategies["split"] = [f for t in truths for f in fx.split_findings(t)]
    else:
        strategies["split"] = [noise, noise]
    return strategies


def score_rows():
    config = load_scoring_config()
    rows = []
    for scenario, kind, anomaly_type, truths in build_corpus():
        strategies = submissions_for(kind, truths)
        for strategy, findings in strategies.items():
            reward = compute_reward(findings, truths, BASELINE_STEPS, config=config)
            rows.append(
                {
                    "scenario": scenario,
                    "strategy": strategy,
                    "kind": kind,
                    "anomaly_type": anomaly_type,
                    "tp": reward.tp,
                    "fp": reward.fp,
                    "fn": reward.fn,
                    "steps_used": reward.steps_used,
                    "reward_exact": str(reward.reward),
                    "reward_decimal": reward.to_dict()["reward_decimal"],
                    "eta_exact": str(reward.eta),
                }
            )
    # P5 sweep: equal completeness, varying steps (dirty scenario).
    _, _, _, truths = build_corpus()[2]
    findings = [fx.honest_finding(t) for t in truths]
    for steps in P5_STEP_SWEEP:
        reward = compute_reward(findings, truths, steps, config=config)
        rows.append(
            {
                "scenario": "dup-1",
                "strategy": "honest",
                "kind": "dirty",
                "anomaly_type": "DUPLICATE_PAYMENT",
                "tp": reward.tp,
                "fp": reward.fp,
                "fn": reward.fn,
                "steps_used": steps,
                "reward_exact": str(reward.reward),
                "reward_decimal": reward.to_dict()["reward_decimal"],
                "eta_exact": str(reward.eta),
            }
        )
    return rows


class TestRewardProperties(unittest.TestCase):
    """TZ 15.7 P1-P5 over the corpus + automatic matrix artifact."""

    @classmethod
    def setUpClass(cls):
        cls.rows = score_rows()
        cls.matrix = build_reward_property_matrix(cls.rows)
        cls.verdicts = evaluate_reward_properties(cls.matrix)
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        artifact = dict(cls.matrix)
        # TZ §23.5: every report carries code version, config hash, run
        # timestamp, target platform, Python version, and the launch command.
        artifact.update(
            {
                "schema_version": "1.0.0",
                "report_type": "reward_property_matrix",
                "code_version": "twinledger@1.0.0",
                "config_hash": sha256_hex(
                    {"baseline_steps": BASELINE_STEPS, "p5_step_sweep": list(P5_STEP_SWEEP)}
                ),
                "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "platform": platform.platform(),
                "python_version": sys.version.split()[0],
                "command": "python3 -m unittest tests.scoring.test_reward_properties",
            }
        )
        artifact["properties"] = cls.verdicts
        ARTIFACT_PATH.write_text(canonical_json(artifact) + "\n", encoding="utf-8")

    def test_matrix_artifact_written(self):
        self.assertTrue(ARTIFACT_PATH.is_file())
        parsed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
        self.assertIn("rows", parsed)
        self.assertIn("properties", parsed)
        self.assertTrue(parsed["provisional"])

    def test_p1_correct_answer_beats_silence_on_dirty(self):
        verdict = self.verdicts["P1"]
        self.assertTrue(verdict["checks"], "P1 needs dirty scenarios")
        for check in verdict["checks"]:
            self.assertTrue(check["pass"], check)
        self.assertTrue(verdict["pass"])

    def test_p2_silence_beats_false_accusations_on_clean(self):
        verdict = self.verdicts["P2"]
        self.assertTrue(verdict["checks"], "P2 needs clean scenarios")
        for check in verdict["checks"]:
            self.assertTrue(check["pass"], check)
        self.assertTrue(verdict["pass"])

    def test_p3_duplicates_and_splits_give_no_advantage(self):
        verdict = self.verdicts["P3"]
        self.assertGreaterEqual(len(verdict["checks"]), 8)
        for check in verdict["checks"]:
            self.assertTrue(check["pass"], check)
        self.assertTrue(verdict["pass"])

    def test_p4_flag_all_worse_than_honest(self):
        verdict = self.verdicts["P4"]
        self.assertEqual(len(verdict["checks"]), 1)
        self.assertTrue(verdict["checks"][0]["pass"], verdict["checks"][0])
        self.assertTrue(verdict["pass"])

    def test_p5_step_penalty_bounded_by_official_weight(self):
        # BUG-TL-0001: the bound is the official penalty weight 0.2, not the
        # superseded provisional eta=0.05 (configs/scoring/default.json is a
        # frozen contract and still carries eta, which no longer drives R).
        verdict = self.verdicts["P5"]
        self.assertTrue(verdict["checks"], "P5 needs a steps sweep")
        for check in verdict["checks"]:
            self.assertTrue(check["non_increasing"], check)
            self.assertLessEqual(
                Fraction(check["max_spread"]),
                OFFICIAL_STEP_PENALTY_WEIGHT,
                "total step penalty exceeds the official weight",
            )
        self.assertTrue(verdict["pass"])

    def test_p5_full_budget_penalty_equals_official_weight(self):
        config = load_scoring_config()
        _, _, _, truths = build_corpus()[2]
        findings = [fx.honest_finding(t) for t in truths]
        perfect = compute_reward(findings, truths, 0, config=config)
        full = compute_reward(findings, truths, config.max_steps, config=config)
        self.assertEqual(perfect.penalty, Fraction(0))
        self.assertEqual(full.penalty, OFFICIAL_STEP_PENALTY_WEIGHT)
        self.assertEqual(perfect.reward - full.reward, OFFICIAL_STEP_PENALTY_WEIGHT)

    def test_all_five_properties_pass(self):
        for property_id in ("P1", "P2", "P3", "P4", "P5"):
            with self.subTest(property_id=property_id):
                self.assertTrue(self.verdicts[property_id]["pass"])

    def test_summary_uses_exact_arithmetic(self):
        summary = self.matrix["summary"]
        self.assertIn("honest", summary)
        values = [
            Fraction(row["reward_exact"])
            for row in self.rows
            if row["strategy"] == "honest"
        ]
        mean = sum(values, Fraction(0)) / len(values)
        self.assertEqual(summary["honest"]["mean_reward_exact"], str(mean))


if __name__ == "__main__":
    unittest.main()
