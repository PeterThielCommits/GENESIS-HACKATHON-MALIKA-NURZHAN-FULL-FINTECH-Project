"""Security, sealed boundary, canary non-leakage, and isolation profile tests (Phase 9, Task 9.8)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gen.pipeline import build_episode, default_dataset_recipes
from harness.protocol import LeakageViolationError, assert_policy_outbound_clean
from harness.runner import run_closed_eval_episode
from harness.sandbox import (
    StagedPublicWorkspace,
    build_sanitized_env,
    detect_security_profile,
)
from harness.trajectory import load_recorded_trajectory_jsonl
from tools.check_import_boundaries import scan


class TestPhase09IsolationAndSecurity(unittest.TestCase):
    def test_security_profile_honesty_and_env_sanitization(self) -> None:
        profile = detect_security_profile()
        # Subprocess isolation alone MUST NEVER claim full OS sandbox (P-012, R-09)
        self.assertFalse(profile.is_full_os_sandbox)
        self.assertIn("separate_os_subprocesses_policy_env_scorer", profile.enforced_controls)
        self.assertIn("staged_readonly_public_dir_without_sealed", profile.enforced_controls)
        self.assertIn("ephemeral_empty_policy_cwd_without_episodes", profile.enforced_controls)
        self.assertGreater(len(profile.unavailable_controls), 0)

        fake_env = {
            "PATH": "/usr/bin:/bin",
            "TWINLEDGER_CANARY_SECRET": "CANARY_991122",
            "COMMITMENT_SALT_HEX": "deadbeef" * 8,
            "EPISODE_SEED": "2025",
            "GITHUB_TOKEN": "ghp_secret",
        }
        with mock.patch.dict(os.environ, fake_env, clear=False):
            clean_env = build_sanitized_env(role="POLICY")
        for bad_key in ("TWINLEDGER_CANARY_SECRET", "COMMITMENT_SALT_HEX", "EPISODE_SEED", "GITHUB_TOKEN"):
            self.assertNotIn(bad_key, clean_env)
        self.assertEqual(clean_env["TWINLEDGER_PROCESS_ROLE"], "POLICY")

    def test_staged_public_workspace_readonly_and_rejects_bad_entries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tl_sec_ws_") as td:
            root = Path(td)
            ep = build_episode(default_dataset_recipes("dev", master_seed=2025)[0], root).episode_dir

            with StagedPublicWorkspace(ep / "public") as ws:
                # Zero sealed/truth/provenance anywhere in staged workspace
                all_names = {p.name for p in ws.root_dir.rglob("*")}
                self.assertNotIn("sealed", all_names)
                self.assertNotIn("truth.json", all_names)
                self.assertNotIn("provenance.json", all_names)
                self.assertNotIn("manifest.json", all_names)

                # If non-root, writing into staged public/ MUST fail with PermissionError
                if hasattr(os, "geteuid") and os.geteuid() != 0:
                    with self.assertRaises(PermissionError):
                        (ws.public_dir / "injected.json").write_text("{}", encoding="utf-8")
                    with self.assertRaises(PermissionError):
                        (ws.public_dir / "company.json").write_text("{}", encoding="utf-8")

            # Cleaned up completely upon context exit
            self.assertFalse((root / "nonexistent").exists())

            # Reject index_hints.json, dotfiles, and symlinks
            bad_pub = root / "bad_public"
            shutil.copytree(ep / "public", bad_pub)
            (bad_pub / "index_hints.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                with StagedPublicWorkspace(bad_pub):
                    pass

            (bad_pub / "index_hints.json").unlink()
            (bad_pub / ".hidden_seed").write_text("1", encoding="utf-8")
            with self.assertRaises(ValueError):
                with StagedPublicWorkspace(bad_pub):
                    pass

            (bad_pub / ".hidden_seed").unlink()
            outside = root / "outside_secret.json"
            outside.write_text("{}", encoding="utf-8")
            (bad_pub / "company.json").unlink()
            (bad_pub / "company.json").symlink_to(outside)
            with self.assertRaises(ValueError):
                with StagedPublicWorkspace(bad_pub):
                    pass

    def test_malicious_policy_probe_blocked_and_zero_canary_leakage(self) -> None:
        canary = "CANARY_TOKEN_PHASE09_7F8E9D0A"
        with tempfile.TemporaryDirectory(prefix="tl_sec_probe_") as td:
            root = Path(td)
            ep = build_episode(default_dataset_recipes("dev", master_seed=2025)[1], root).episode_dir

            # Inject canary into sealed/provenance.json without touching truth.json
            prov_path = ep / "sealed" / "provenance.json"
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            prov["internal_canary"] = canary
            prov_path.write_text(json.dumps(prov), encoding="utf-8")

            with mock.patch.dict(os.environ, {"SECRET_CANARY_ENV": canary}, clear=False):
                res = run_closed_eval_episode(
                    episode_dir=ep,
                    policy_argv=[
                        sys.executable,
                        "-m",
                        "harness.reference_policies",
                        "--policy",
                        "malicious_probe_v1",
                    ],
                    policy_id="malicious_probe_v1",
                    artifacts_dir=root / "art",
                    canary_tokens=(canary,),
                )

            self.assertTrue(res.terminated)
            self.assertEqual(res.receipt["verification_status"], "VERIFIED")

            # Inspect the status tag emitted by malicious_probe_v1 in its final submit request_id
            entries = load_recorded_trajectory_jsonl(res.trajectory_path)
            submit_entries = [e for e in entries if e.trajectory_event.event_type == "submit"]
            self.assertEqual(len(submit_entries), 1)
            submit_req = json.loads(submit_entries[0].canonical_action_json)
            req_id = submit_req["request_id"]

            self.assertIn("cwd_empty=True", req_id)
            if hasattr(os, "geteuid") and os.geteuid() != 0:
                self.assertIn("cwd_writable=False", req_id)
            self.assertIn("env_leaks=0", req_id)
            self.assertIn("sealed_found=False", req_id)
            self.assertIn("trav_blocked=True", req_id)
            self.assertIn("calc_blocked=True", req_id)

            # Verify canary never appeared in trajectory or receipt
            traj_text = res.trajectory_path.read_text(encoding="utf-8")
            rcpt_text = res.receipt_path.read_text(encoding="utf-8")
            self.assertNotIn(canary, traj_text)
            self.assertNotIn(canary, rcpt_text)

    def test_outbound_policy_leak_guard_blocks_private_markers(self) -> None:
        for bad_payload in (
            '{"obs":"../sealed/truth.json"}',
            '{"obs":"provenance.json"}',
            '{"truth_commitment":"abc"}',
            '{"note":"CANARY_XYZ"}',
        ):
            with self.assertRaises(LeakageViolationError):
                assert_policy_outbound_clean(bad_payload, extra_forbidden_tokens=("CANARY_XYZ",))

    def test_import_boundary_scanner_catches_seal_and_harness_violations(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tl_ast_p9_") as td:
            root = Path(td)
            (root / "seal").mkdir()
            (root / "seal" / "bad.py").write_text("import scoring\n", encoding="utf-8")
            (root / "harness").mkdir()
            (root / "harness" / "bad.py").write_text("from seal import MerkleTree\n", encoding="utf-8")
            violations = scan(root)
            self.assertTrue(any("seal/bad.py" in v for v in violations))
            self.assertTrue(any("harness/bad.py" in v for v in violations))


if __name__ == "__main__":
    unittest.main()
