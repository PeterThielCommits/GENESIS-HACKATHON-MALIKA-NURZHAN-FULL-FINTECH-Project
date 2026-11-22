"""Full-trajectory replay tests (Phase 16, task 16.4; TZ §16).

The published trajectories are a *claim*: every recorded observation, reward
and score is reproducible. These tests prove the checker both accepts the real
log and rejects a tampered one -- a determinism gate that cannot fail is not a
determinism gate.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import replay_all_trajectories as rp

TRAJ = rp.TRAJECTORIES
# The committed trajectory log is the input; the report is a gitignored output,
# so gating on it skipped everything on a clean clone (see Phase 15 D-15-01).
TRAJ_READY = TRAJ.is_file()


def setUpModule() -> None:
    if TRAJ_READY:
        print("replay-all: trajectories present - integration checks are active in this run")
    else:
        print("replay-all: trajectories absent - integration checks skip explicitly (bootstrap position)")


class TestMechanism(unittest.TestCase):
    def test_missing_log_is_a_configuration_error(self):
        with self.assertRaises(FileNotFoundError):
            rp.load_trajectories(Path("/nonexistent/trajectories.jsonl"))

    def test_empty_log_is_rejected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.jsonl"
            path.write_text("\n\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                rp.load_trajectories(path)

    def test_unparseable_line_names_its_line_number(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.jsonl"
            path.write_text('{"a": 1}\nnot json\n', encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                rp.load_trajectories(path)
        self.assertIn(":2:", str(ctx.exception))

    def test_tool_is_not_in_the_frozen_evidence_set(self):
        self.assertNotIn("reports/latest", str(rp.OUTPUT_PATH))

    def test_console_output_is_ascii(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rp._say("a \u2014 b \u2192 c \u00a7 d")
        self.assertEqual(buffer.getvalue(), "a - b -> c S d\n")
        buffer.getvalue().encode("ascii")


class TestPublishedTrajectories(unittest.TestCase):
    @unittest.skipUnless(TRAJ_READY, "trajectories not generated yet")
    def test_every_run_replays_byte_identically(self):
        report = rp.replay_all()
        self.assertEqual(report["status"], "PASS", json.dumps(report["failures"][:2], indent=2))
        self.assertEqual(report["runs_replayed"], 80)
        self.assertEqual(report["runs_matched"], 80)
        self.assertGreaterEqual(report["steps_replayed"], 500)

    @unittest.skipUnless(TRAJ_READY, "trajectories not generated yet")
    def test_report_written_by_the_cli_matches_a_fresh_replay(self):
        """Write the report through the real CLI into a temp dir, then compare.

        Never read rp.OUTPUT_PATH here: it lives under a gitignored directory, so
        on a clean clone it does not exist and RC-001 would error (found by the
        TZ 16.2 clean-clone run). The CLI is exercised for real, just elsewhere.
        """
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "trajectory_replay.json"
            rc = rp.main(["--output", str(out)])
            self.assertEqual(rc, 0)
            published = json.loads(out.read_text(encoding="utf-8"))
        fresh = rp.replay_all()
        self.assertEqual(published["runs_replayed"], fresh["runs_replayed"])
        self.assertEqual(published["status"], "PASS")
        self.assertEqual(fresh["status"], "PASS")

    @unittest.skipUnless(TRAJ_READY, "trajectories not generated yet")
    def test_a_tampered_metric_is_detected(self):
        rows = copy.deepcopy(rp.load_trajectories())
        rows[0]["metrics"]["return"] = 999.0
        report = rp.replay_all(trajectories=rows)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["runs_matched"], report["runs_replayed"] - 1)
        self.assertIn("score.return", report["failures"][0]["problems"][0])

    @unittest.skipUnless(TRAJ_READY, "trajectories not generated yet")
    def test_a_tampered_observation_is_detected(self):
        rows = copy.deepcopy(rp.load_trajectories())
        rows[0]["steps"][0]["observation"] = {"tampered": True}
        report = rp.replay_all(trajectories=rows)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("observation differs", report["failures"][0]["problems"][0])

    @unittest.skipUnless(TRAJ_READY, "trajectories not generated yet")
    def test_unknown_episode_is_detected(self):
        rows = copy.deepcopy(rp.load_trajectories())
        rows[0]["episode_id"] = "D99_not_a_scenario"
        report = rp.replay_all(trajectories=rows)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("not generated", report["failures"][0]["problems"][0])

    @unittest.skipUnless(TRAJ_READY, "trajectories not generated yet")
    def test_covered_policies_and_episodes(self):
        rows = rp.load_trajectories()
        self.assertEqual(len({r["episode_id"] for r in rows}), 20)
        self.assertEqual({r["policy"] for r in rows}, {"random", "simple_reconciliation", "mass_flagging", "oracle"})


if __name__ == "__main__":
    unittest.main()
