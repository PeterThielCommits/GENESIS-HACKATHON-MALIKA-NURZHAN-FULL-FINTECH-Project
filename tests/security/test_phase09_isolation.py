"""Security, kernel-namespace/seccomp isolation, CSPRNG rekey, and semantic truth tests."""

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
    probe_kernel_sandbox_capabilities,
)
from harness.trajectory import load_recorded_trajectory_jsonl
from seal.commitment import compute_commitment
from seal.rekey import rekey_episode_with_production_salt
from tools.check_import_boundaries import scan


class TestPhase09IsolationAndSecurity(unittest.TestCase):
    def test_security_profile_kernel_and_fallback_honesty(self) -> None:
        caps = probe_kernel_sandbox_capabilities()
        profile = detect_security_profile()
        self.assertIn("separate_os_subprocesses_policy_env_scorer", profile.enforced_controls)
        self.assertIn("staged_readonly_public_dir_without_sealed", profile.enforced_controls)

        if caps.available:
            self.assertTrue(profile.is_full_os_sandbox)
            self.assertEqual(profile.profile_id, "linux-kernel-ns-seccomp-v1")
            expected_unavail = ("non_root_uid",) if (hasattr(os, "geteuid") and os.geteuid() == 0) else ()
            self.assertEqual(profile.unavailable_controls, expected_unavail)
            self.assertIn("linux_user_mount_namespace_masked_sealed_tmpfs", profile.enforced_controls)
            self.assertIn("seccomp_bpf_syscall_filter", profile.enforced_controls)

        # Fallback non-kernel profile MUST report is_full_os_sandbox=False (P-012, R-09)
        fallback = detect_security_profile(force_non_kernel=True)
        self.assertFalse(fallback.is_full_os_sandbox)
        self.assertGreater(len(fallback.unavailable_controls), 0)

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
                all_names = {p.name for p in ws.root_dir.rglob("*")}
                self.assertNotIn("sealed", all_names)
                self.assertNotIn("truth.json", all_names)
                self.assertNotIn("provenance.json", all_names)
                self.assertNotIn("manifest.json", all_names)

                if hasattr(os, "geteuid") and os.geteuid() != 0:
                    with self.assertRaises(PermissionError):
                        (ws.public_dir / "injected.json").write_text("{}", encoding="utf-8")
                    with self.assertRaises(PermissionError):
                        (ws.public_dir / "company.json").write_text("{}", encoding="utf-8")

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

    def test_malicious_policy_blocked_even_with_exact_host_sealed_path(self) -> None:
        canary = "CANARY_TOKEN_PHASE09_7F8E9D0A"
        caps = probe_kernel_sandbox_capabilities()
        with tempfile.TemporaryDirectory(prefix="tl_sec_probe_") as td:
            root = Path(td)
            ep = build_episode(default_dataset_recipes("dev", master_seed=2025)[1], root).episode_dir
            exact_truth_path = str((ep / "sealed" / "truth.json").resolve())

            prov_path = ep / "sealed" / "provenance.json"
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            prov["internal_canary"] = canary
            prov_path.write_text(json.dumps(prov), encoding="utf-8")

            policy_cmd = [
                sys.executable,
                "-m",
                "harness.reference_policies",
                "--policy",
                "malicious_probe_v1",
            ]
            if caps.available:
                # Even when handed the EXACT absolute host path to sealed/truth.json,
                # the Linux mount-namespace tmpfs mask must hide it!
                policy_cmd.extend(["--known-sealed-path", exact_truth_path])

            with mock.patch.dict(os.environ, {"SECRET_CANARY_ENV": canary}, clear=False):
                res = run_closed_eval_episode(
                    episode_dir=ep,
                    policy_argv=policy_cmd,
                    policy_id="malicious_probe_v1",
                    artifacts_dir=root / "art",
                    canary_tokens=(canary,),
                )

            self.assertTrue(res.terminated)
            self.assertEqual(res.receipt["verification_status"], "VERIFIED")

            entries = load_recorded_trajectory_jsonl(res.trajectory_path)
            submit_entries = [e for e in entries if e.trajectory_event.event_type == "submit"]
            self.assertEqual(len(submit_entries), 1)
            submit_req = json.loads(submit_entries[0].canonical_action_json)
            req_id = submit_req["request_id"]

            self.assertIn("cwd_empty=True", req_id)
            self.assertIn("cwd_writable=False", req_id)
            self.assertIn("env_leaks=0", req_id)
            self.assertIn("sealed_found=False", req_id)
            self.assertIn("trav_blk=True", req_id)
            self.assertIn("calc_blk=True", req_id)
            if caps.available:
                self.assertIn("net_blk=True", req_id)
                self.assertIn("umnt_blk=True", req_id)

            traj_text = res.trajectory_path.read_text(encoding="utf-8")
            rcpt_text = res.receipt_path.read_text(encoding="utf-8")
            self.assertNotIn(canary, traj_text)
            self.assertNotIn(canary, rcpt_text)

    def test_production_csprng_rekey_and_semantic_truth_verification(self) -> None:
        from tools.make_dataset import build_and_verify_split

        with tempfile.TemporaryDirectory(prefix="tl_prod_rekey_") as td:
            root = Path(td)
            recipe = default_dataset_recipes("dev", master_seed=2025)[1]
            build_and_verify_split("dev", root, recipes=[recipe])
            ep = next(p for p in sorted(root.iterdir()) if p.is_dir())

            # 1. Rekey episode to PRODUCTION_SECRET CSPRNG salt
            rk = rekey_episode_with_production_salt(ep)
            self.assertTrue(rk.verified)
            self.assertEqual(rk.salt_mode, "PRODUCTION_SECRET")
            self.assertNotEqual(rk.old_commitment, rk.new_commitment)

            res = run_closed_eval_episode(
                episode_dir=ep,
                policy_argv=[sys.executable, "-m", "harness.reference_policies", "--policy", "rule_auditor_v1"],
                policy_id="rule_auditor_v1",
                artifacts_dir=root / "art_prod",
                salt_mode="PRODUCTION_SECRET",
            )
            self.assertEqual(res.receipt["verification_status"], "VERIFIED")
            self.assertEqual(res.score_report["salt_reveal"]["mode"], "PRODUCTION_SECRET")
            self.assertEqual(res.score_report["semantic_truth_verification"]["status"], "VERIFIED")
            self.assertEqual(
                res.score_report["contract_v1_score"]["diagnostics"]["explanation_consistency"]["status"],
                "EVALUATED",
            )
            self.assertIn(
                "metrics",
                res.score_report["contract_v1_score"]["diagnostics"]["verifier_quality"],
            )

            # 2. Forge a semantically wrong truth [] WITH a matching commitment (re-committed!)
            # Commit-reveal passes, BUT semantic_truth_verification (Stage-2 crosscheck) MUST REJECT!
            ep_sem_bad = root / "ep_sem_bad"
            shutil.copytree(ep, ep_sem_bad)
            (ep_sem_bad / "sealed" / "truth.json").write_text("[]\n", encoding="utf-8")
            prov = json.loads((ep_sem_bad / "sealed" / "provenance.json").read_text(encoding="utf-8"))
            forged_commit = compute_commitment([], prov["commitment_salt_hex"])
            man = json.loads((ep_sem_bad / "manifest.json").read_text(encoding="utf-8"))
            man["truth_commitment"] = forged_commit
            (ep_sem_bad / "manifest.json").write_text(json.dumps(man), encoding="utf-8")

            with self.assertRaises(RuntimeError) as ctx:
                run_closed_eval_episode(
                    episode_dir=ep_sem_bad,
                    policy_argv=[sys.executable, "-m", "harness.reference_policies", "--policy", "silent_v1"],
                    policy_id="silent_v1",
                    artifacts_dir=root / "art_forged",
                    salt_mode="PRODUCTION_SECRET",
                )
            self.assertIn("exit_code=4", str(ctx.exception))
            forged_score_file = next((root / "art_forged").glob("*.score_report.json"))
            forged_score = json.loads(forged_score_file.read_text(encoding="utf-8"))
            self.assertEqual(forged_score["verification_status"], "REJECTED")
            self.assertEqual(forged_score["commit_reveal"]["verified"], True)
            self.assertEqual(forged_score["semantic_truth_verification"]["status"], "REJECTED")

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
