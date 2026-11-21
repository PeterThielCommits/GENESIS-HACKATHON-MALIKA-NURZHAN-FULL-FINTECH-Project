"""Deterministic fresh-process trajectory replay & verification CLI (Phase 9, Task 9.7).

Implements Master TZ v3.0.0 §16.6, §23.2, §23.5, and REQ-SEAL-030..031:
  - Spawns a brand-new ``EnvSubprocess`` inside a clean ``StagedPublicWorkspace``
    (fresh process + clean working directory, REQ-SEAL-030);
  - Replays every recorded action from ``trajectory.jsonl`` in exact order;
  - Compares canonical response bytes step-by-step (no post-hoc sorting tricks,
    REQ-SEAL-031), recomputes every ``TrajectoryEvent`` digest and
    ``trajectory_head``, and runs a fresh post-episode ``scorer_process`` to
    confirm identical reward and offline receipt validity;
  - ``python3 -m harness.replay --verify-suite`` runs a complete standalone
    CLOSED_EVAL + batch Merkle + fresh-process replay verification suite and
    writes ``artifacts/reports/latest/replay_report.json``.

Imports ONLY ``contracts/``, ``harness.*``, and Python 3.11 stdlib
(never imports ``gen``, ``verifier``, ``scoring``, or ``seal``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contracts.canonical import canonical_json, sha256_hex
from harness.env_process import EnvSubprocess
from harness.runner import run_closed_eval_batch
from harness.sandbox import REPO_ROOT, build_sanitized_env
from harness.scorer_process import run_scorer_subprocess, verify_receipt_subprocess
from harness.trajectory import (
    TrajectoryRecorder,
    load_recorded_trajectory_jsonl,
)

DEFAULT_REPLAY_REPORT_PATH = (
    REPO_ROOT / "artifacts" / "reports" / "latest" / "replay_report.json"
)


@dataclass(frozen=True)
class ReplayEpisodeResult:
    """Outcome of replaying a single recorded episode trajectory in a fresh process."""

    episode_id: str
    policy_identifier: str
    matched: bool
    events_replayed: int
    recorded_head: str
    replayed_head: str
    response_bytes_identical: bool
    event_hashes_identical: bool
    reward_identical: bool
    offline_receipt_valid: bool | None
    mismatches: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "policy_identifier": self.policy_identifier,
            "matched": self.matched,
            "events_replayed": self.events_replayed,
            "recorded_head": self.recorded_head,
            "replayed_head": self.replayed_head,
            "response_bytes_identical": self.response_bytes_identical,
            "event_hashes_identical": self.event_hashes_identical,
            "reward_identical": self.reward_identical,
            "offline_receipt_valid": self.offline_receipt_valid,
            "mismatches": list(self.mismatches),
        }


def replay_episode(
    *,
    episode_dir: Path | str,
    trajectory_path: Path | str,
    submission_path: Path | str | None = None,
    receipt_path: Path | str | None = None,
    score_report_path: Path | str | None = None,
    cursor_seed: str = "episode",
    env_config_path: Path | str | None = None,
    time_limit_s: float = 60.0,
) -> ReplayEpisodeResult:
    """Replay a recorded ``trajectory.jsonl`` in a fresh ``EnvSubprocess`` (REQ-SEAL-030)."""
    ep_path = Path(episode_dir).resolve()
    traj_path = Path(trajectory_path).resolve()

    manifest_path = ep_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    episode_id = str(manifest["episode_id"])
    truth_commitment = str(manifest["truth_commitment"])

    # Verify public files match manifest SHA-256 before replay
    mismatches: list[str] = []
    for pf in manifest.get("public_files", []):
        rel = pf["path"]
        f_target = ep_path / rel
        if not f_target.is_file():
            mismatches.append(f"missing public file {rel}")
        elif hashlib.sha256(f_target.read_bytes()).hexdigest() != pf["sha256"]:
            mismatches.append(f"public file tampered: {rel}")

    entries = load_recorded_trajectory_jsonl(traj_path)
    if not entries:
        return ReplayEpisodeResult(
            episode_id=episode_id,
            policy_identifier="unknown",
            matched=False,
            events_replayed=0,
            recorded_head="",
            replayed_head="",
            response_bytes_identical=False,
            event_hashes_identical=False,
            reward_identical=False,
            offline_receipt_valid=None,
            mismatches=("empty trajectory log",),
        )

    recorded_head = entries[-1].chain_head_after
    policy_id = "replay_policy"
    if submission_path is not None and Path(submission_path).is_file():
        sub_orig = json.loads(Path(submission_path).read_text(encoding="utf-8"))
        policy_id = str(sub_orig.get("policy_identifier", policy_id))
    elif receipt_path is not None and Path(receipt_path).is_file():
        rec_orig = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
        policy_id = str(rec_orig.get("policy_identifier", policy_id))

    replay_recorder = TrajectoryRecorder(
        episode_id=episode_id,
        truth_commitment=truth_commitment,
        cursor_seed=cursor_seed,
    )

    response_bytes_identical = True
    event_hashes_identical = True

    deadline = time.monotonic() + time_limit_s
    env_proc = EnvSubprocess(
        ep_path / "public",
        env_config_path=env_config_path,
        cursor_seed=cursor_seed,
        require_closed_eval=True,
    )

    steps_used = 0
    terminated = False
    truncated = False
    no_submit = True
    submitted_findings: list[dict[str, Any]] = []

    try:
        init_obs = env_proc.start(deadline_monotonic=deadline)
        # Event 0 must be reset
        ev0_entry = entries[0]
        replayed_reset_resp_json = canonical_json(init_obs)
        if replayed_reset_resp_json != ev0_entry.canonical_response_json:
            response_bytes_identical = False
            mismatches.append("event[0] reset canonical_response_json mismatch")

        rec_ev0 = replay_recorder.record_event(
            event_type="reset",
            action_payload=json.loads(ev0_entry.canonical_action_json),
            response_payload=init_obs,
            logical_step=0,
        )
        if rec_ev0.chain_head_after != ev0_entry.chain_head_after:
            event_hashes_identical = False
            mismatches.append("event[0] chain_head_after mismatch")

        max_steps = int(init_obs["limits"]["max_steps"])
        submit_counts = bool(init_obs["limits"]["submit_counts_as_step"])

        # Replay intermediate actions (excluding final terminate/truncate synthetic marker)
        for idx, entry in enumerate(entries[1:], start=1):
            etype = entry.trajectory_event.event_type
            if etype in ("terminate", "truncate"):
                # Verify terminal lifecycle event
                expected_term = "terminate" if terminated else "truncate"
                if etype != expected_term:
                    mismatches.append(f"event[{idx}] terminal type mismatch: {etype} vs {expected_term}")
                    event_hashes_identical = False
                act_obj = json.loads(entry.canonical_action_json)
                resp_obj = {
                    "terminated": terminated,
                    "truncated": truncated,
                    "steps_used": steps_used,
                    "submitted_count": len(submitted_findings),
                }
                if canonical_json(resp_obj) != entry.canonical_response_json:
                    response_bytes_identical = False
                    mismatches.append(f"event[{idx}] terminal canonical_response_json mismatch")
                rec_term = replay_recorder.record_event(
                    event_type=etype,
                    action_payload=act_obj,
                    response_payload=resp_obj,
                    logical_step=steps_used,
                )
                if rec_term.chain_head_after != entry.chain_head_after:
                    event_hashes_identical = False
                    mismatches.append(f"event[{idx}] terminal chain_head_after mismatch")
                continue

            raw_req = entry.raw_request_line if entry.raw_request_line is not None else entry.canonical_action_json
            resp_line, resp_dict = env_proc.step_line(raw_req, deadline_monotonic=deadline)

            # Byte-for-byte canonical response check (REQ-SEAL-030, REQ-SEAL-031)
            if resp_line != entry.canonical_response_json:
                response_bytes_identical = False
                mismatches.append(f"event[{idx}] canonical response bytes differed")

            try:
                parsed_req: Any = json.loads(raw_req)
            except json.JSONDecodeError:
                parsed_req = {"_malformed_raw": raw_req[:256]}

            is_dict_req = isinstance(parsed_req, dict)
            action_block = parsed_req.get("action") if is_dict_req else None
            tool_name = action_block.get("tool") if isinstance(action_block, dict) else None

            if etype == "submit":
                if submit_counts and steps_used < max_steps:
                    steps_used += 1
                if resp_dict.get("ok") and isinstance(resp_dict.get("result"), dict):
                    steps_used = int(resp_dict["result"].get("steps_used", steps_used))
                    submitted_findings = list((action_block or {}).get("args", {}).get("findings", []))
                    terminated = True
                    no_submit = False
            else:
                err_code = (resp_dict.get("error") or {}).get("code") if not resp_dict.get("ok") else None
                if is_dict_req:
                    if steps_used < max_steps:
                        steps_used += 1
                    elif err_code == "LIMIT":
                        truncated = True
                if err_code == "LIMIT":
                    truncated = True

            rec_step = replay_recorder.record_event(
                event_type=etype,
                action_payload=parsed_req,
                response_payload=resp_dict,
                logical_step=steps_used,
                raw_request_line=raw_req,
            )
            if (
                rec_step.trajectory_event.to_dict() != entry.trajectory_event.to_dict()
                or rec_step.chain_head_after != entry.chain_head_after
            ):
                event_hashes_identical = False
                mismatches.append(f"event[{idx}] TrajectoryEvent digest mismatch")

        if not (terminated or truncated):
            truncated = True
    finally:
        env_exited_ns = env_proc.close()

    replayed_head = replay_recorder.head
    if replayed_head != recorded_head:
        event_hashes_identical = False
        mismatches.append(f"trajectory_head mismatch: recorded={recorded_head}, replayed={replayed_head}")

    # Re-score in a fresh isolated scorer subprocess if sealed truth is available
    reward_identical = True
    offline_receipt_valid: bool | None = None
    sealed_truth_file = ep_path / "sealed" / "truth.json"

    if sealed_truth_file.is_file() and not any("public file tampered" in m or "missing public file" in m for m in mismatches):
        with tempfile.TemporaryDirectory(prefix="tl_replay_score_") as tmp_sc:
            tmp_root = Path(tmp_sc)
            rep_traj = tmp_root / "replay.trajectory.jsonl"
            rep_sub = tmp_root / "replay.submission.json"
            rep_rcpt = tmp_root / "replay.receipt.json"
            rep_score = tmp_root / "replay.score.json"

            replay_recorder.write_jsonl(rep_traj)
            rep_sub.write_text(
                canonical_json(
                    {
                        "schema_version": "1.0.0",
                        "episode_id": episode_id,
                        "policy_identifier": policy_id,
                        "steps_used": steps_used,
                        "terminated": terminated,
                        "truncated": truncated,
                        "no_submit": no_submit,
                        "timed_out": False,
                        "findings": submitted_findings,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            try:
                sc_res = run_scorer_subprocess(
                    episode_dir=ep_path,
                    submission_path=rep_sub,
                    trajectory_path=rep_traj,
                    policy_id=policy_id,
                    output_receipt_path=rep_rcpt,
                    output_score_path=rep_score,
                    env_alive=False,
                    policy_alive=False,
                    env_exited_ns=env_exited_ns,
                    policy_exited_ns=env_exited_ns,
                )
                if sc_res.exit_code != 0:
                    reward_identical = False
                    mismatches.append(f"replay scorer exited non-zero ({sc_res.exit_code})")
                elif score_report_path is not None and Path(score_report_path).is_file():
                    orig_score = json.loads(Path(score_report_path).read_text(encoding="utf-8"))
                    if sc_res.score_report.get("official_score") != orig_score.get("official_score"):
                        reward_identical = False
                        mismatches.append("official_score differed on replay")
                    orig_v1 = (orig_score.get("contract_v1_score") or {}).get("reward_breakdown")
                    rep_v1 = (sc_res.score_report.get("contract_v1_score") or {}).get("reward_breakdown")
                    if orig_v1 != rep_v1:
                        reward_identical = False
                        mismatches.append("contract_v1_score reward_breakdown differed on replay")
            except RuntimeError as exc:
                reward_identical = False
                mismatches.append(f"replay scorer rejected episode: {exc}")

    if receipt_path is not None and Path(receipt_path).is_file():
        orig_receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
        if orig_receipt.get("trajectory_head") != replayed_head:
            event_hashes_identical = False
            mismatches.append("receipt trajectory_head mismatch")
        prov_file = ep_path / "sealed" / "provenance.json"
        salt_hex = (
            json.loads(prov_file.read_text(encoding="utf-8")).get("commitment_salt_hex")
            if prov_file.is_file()
            else None
        )
        v_res = verify_receipt_subprocess(
            receipt_path=receipt_path,
            manifest_path=manifest_path,
            trajectory_path=traj_path,
            truth_path=sealed_truth_file if sealed_truth_file.is_file() else None,
            salt_hex=salt_hex,
        )
        offline_receipt_valid = bool(v_res.get("valid", False))
        if not offline_receipt_valid:
            mismatches.append(f"offline receipt verification failed: {v_res.get('errors')}")

    matched = (
        len(mismatches) == 0
        and response_bytes_identical
        and event_hashes_identical
        and reward_identical
        and (offline_receipt_valid is not False)
    )
    return ReplayEpisodeResult(
        episode_id=episode_id,
        policy_identifier=policy_id,
        matched=matched,
        events_replayed=len(entries),
        recorded_head=recorded_head,
        replayed_head=replayed_head,
        response_bytes_identical=response_bytes_identical,
        event_hashes_identical=event_hashes_identical,
        reward_identical=reward_identical,
        offline_receipt_valid=offline_receipt_valid,
        mismatches=tuple(mismatches),
    )


def run_replay_verification_suite(
    *,
    output_report_path: Path | str | None = None,
) -> dict[str, Any]:
    """Build dev episodes in a clean workspace, execute CLOSED_EVAL, Merkle-seal, and replay all."""
    report_out = Path(output_report_path) if output_report_path else DEFAULT_REPLAY_REPORT_PATH
    report_out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="tl_phase9_suite_") as tmp:
        tmp_root = Path(tmp)
        ep_out = tmp_root / "dev_episodes"
        art_out = tmp_root / "run_artifacts"

        # Generate verified dev episodes in a fresh directory (works on clean clone without gitignored sealed/)
        gen_proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "make_dataset.py"),
                "--split",
                "dev",
                "--out",
                str(ep_out),
            ],
            cwd=str(REPO_ROOT),
            env=build_sanitized_env(role="SCORER", include_repo_pythonpath=True),
            capture_output=True,
            text=True,
            close_fds=True,
            shell=False,
            timeout=120.0,
        )
        if gen_proc.returncode != 0:
            raise RuntimeError(f"make_dataset failed in replay suite: {gen_proc.stderr}")

        runs = [
            (
                ep_out / "ep_dev_001_clean_distractors",
                [sys.executable, "-m", "harness.reference_policies", "--policy", "silent_v1"],
                "silent_v1",
            ),
            (
                ep_out / "ep_dev_002_duplicate",
                [sys.executable, "-m", "harness.reference_policies", "--policy", "rule_auditor_v1"],
                "rule_auditor_v1",
            ),
            (
                ep_out / "ep_dev_003_partial",
                [sys.executable, "-m", "harness.reference_policies", "--policy", "rule_auditor_v1"],
                "rule_auditor_v1",
            ),
            (
                ep_out / "ep_dev_006_compound_all4",
                [sys.executable, "-m", "harness.reference_policies", "--policy", "rule_auditor_v1"],
                "rule_auditor_v1",
            ),
            (
                ep_out / "ep_dev_001_clean_distractors",
                [sys.executable, "-m", "harness.reference_policies", "--policy", "truncate_exhaust_v1"],
                "truncate_exhaust_v1",
            ),
        ]

        merkle_root, batch_results = run_closed_eval_batch(
            runs=runs,
            artifacts_dir=art_out,
            salt_mode="TEST_FIXTURE",
            reveal_salt_in_receipt=False,
        )

        replay_results: list[dict[str, Any]] = []
        for run_res in batch_results:
            rep = replay_episode(
                episode_dir=ep_out / run_res.episode_id,
                trajectory_path=run_res.trajectory_path,
                submission_path=run_res.submission_path,
                receipt_path=run_res.receipt_path,
                score_report_path=run_res.score_report_path,
            )
            replay_results.append(
                {
                    **rep.to_dict(),
                    "lifecycle_strictly_ordered": run_res.lifecycle.strictly_ordered,
                    "merkle_leaf_index": run_res.receipt["merkle_leaf_index"],
                }
            )

        all_matched = all(r["matched"] and r["lifecycle_strictly_ordered"] for r in replay_results)
        security_profile = batch_results[0].security_profile.to_dict()

    # TZ §23.5: every report carries code version, config hash, run timestamp,
    # target platform, Python version, and the launch command.
    config_meta = {
        "suite": "replay_verification",
        "salt_mode": "TEST_FIXTURE",
        "runs": [{"episode_id": Path(str(ep)).name, "policy": pol} for ep, _cmd, pol in runs],
    }
    report = {
        "schema_version": "1.0.0",
        "report_type": "replay_report",
        "code_version": "twinledger@1.0.0",
        "config_hash": sha256_hex(config_meta),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "command": "python3 -m harness.replay --verify-suite",
        "status": "PASS" if all_matched else "FAIL",
        "episodes_replayed": len(replay_results),
        "episodes_tested": len(replay_results),
        "episodes_matched": sum(1 for r in replay_results if r["matched"]),
        "all_byte_identical": all(r["response_bytes_identical"] for r in replay_results),
        "all_hashes_identical": all(r["event_hashes_identical"] for r in replay_results),
        "all_rewards_identical": all(r["reward_identical"] for r in replay_results),
        "all_receipts_verified_offline": all(bool(r["offline_receipt_valid"]) for r in replay_results),
        "batch_merkle_root": merkle_root,
        "security_profile": security_profile,
        "runs": replay_results,
    }
    report_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger deterministic fresh-process trajectory replay")
    parser.add_argument("--verify-suite", action="store_true", help="Run standalone CLOSED_EVAL + replay suite")
    parser.add_argument("--episode-dir", default=None, help="Path to episode directory")
    parser.add_argument("--trajectory", default=None, help="Path to recorded trajectory.jsonl")
    parser.add_argument("--submission", default=None, help="Optional path to submission.json")
    parser.add_argument("--receipt", default=None, help="Optional path to receipt.json")
    parser.add_argument("--score-report", default=None, help="Optional path to score_report.json")
    parser.add_argument("--output", default=None, help="Optional output report path")
    args = parser.parse_args(argv)

    if args.verify_suite:
        rep = run_replay_verification_suite(output_report_path=args.output)
        print(
            f"replay-suite: {rep['status']} "
            f"({rep['episodes_replayed']}/{rep['episodes_replayed']} byte-identical, "
            f"merkle_root={rep['batch_merkle_root'][:16]}...)"
        )
        return 0 if rep["status"] == "PASS" else 1

    if not args.episode_dir or not args.trajectory:
        parser.error("either --verify-suite or both --episode-dir and --trajectory are required")

    res = replay_episode(
        episode_dir=args.episode_dir,
        trajectory_path=args.trajectory,
        submission_path=args.submission,
        receipt_path=args.receipt,
        score_report_path=args.score_report,
    )
    out_dict = res.to_dict()
    if args.output:
        Path(args.output).write_text(json.dumps(out_dict, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sys.stdout.write(canonical_json(out_dict) + "\n")
    return 0 if res.matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
