"""CLOSED_EVAL multi-process episode supervisor (Phase 9, Tasks 9.2, 9.3, 9.6, 9.8).

Implements the full 4-role sealed execution pipeline of Master TZ v3.0.0 §3 & §16:

  P1 POLICY  <--JSONL-->  P0 HARNESS  <--JSONL-->  P2 ENV (staged read-only public/)
                               |
                        append-only TrajectoryRecorder
                               |
                   close P1 POLICY & P2 ENV (barrier)
                               |
                        launch P3 SCORER (post-termination subprocess)
                               |
                   commit-reveal + hash-chain check + reward + Receipt

Imports ONLY ``contracts/``, ``harness.*``, and Python 3.11 stdlib
(never imports ``gen``, ``verifier``, ``scoring``, or ``seal``).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from contracts.canonical import canonical_bytes
from contracts.loader import validate_instance
from harness.env_process import EnvSubprocess
from harness.policy_process import PolicySubprocess
from harness.protocol import MAX_JSONL_LINE_BYTES, assert_policy_outbound_clean
from harness.sandbox import SecurityProfile, detect_security_profile
from harness.scorer_process import (
    ScorerProcessResult,
    run_scorer_subprocess,
    seal_receipt_batch_subprocess,
)
from harness.trajectory import TrajectoryRecorder


def _verify_public_manifest_before_run(episode_dir: Path) -> dict[str, Any]:
    manifest_path = episode_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing manifest.json in {episode_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errs = validate_instance("episode_manifest", manifest)
    if errs:
        raise ValueError(f"invalid manifest.json: {errs[0]}")
    for item in manifest["public_files"]:
        rel = item["path"]
        target = episode_dir / rel
        if not target.is_file():
            raise FileNotFoundError(f"missing public file {rel} in {episode_dir}")
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != item["sha256"]:
            raise ValueError(f"public file SHA-256 mismatch before run: {rel}")
    return manifest


@dataclass(frozen=True)
class ProcessLifecycleProof:
    """Monotonic nanosecond timestamps proving P2 ENV exited before P3 SCORER started."""

    env_started_ns: int
    policy_started_ns: int
    policy_exited_ns: int
    env_exited_ns: int
    scorer_started_ns: int
    scorer_exited_ns: int

    @property
    def strictly_ordered(self) -> bool:
        return (
            self.env_started_ns < self.env_exited_ns <= self.scorer_started_ns <= self.scorer_exited_ns
            and self.policy_started_ns < self.policy_exited_ns <= self.scorer_started_ns
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "env_started_ns": self.env_started_ns,
            "policy_started_ns": self.policy_started_ns,
            "policy_exited_ns": self.policy_exited_ns,
            "env_exited_ns": self.env_exited_ns,
            "scorer_started_ns": self.scorer_started_ns,
            "scorer_exited_ns": self.scorer_exited_ns,
            "strictly_ordered": self.strictly_ordered,
        }


@dataclass(frozen=True)
class ClosedEvalRunResult:
    """Complete outcome of one CLOSED_EVAL multi-process episode run."""

    episode_id: str
    policy_identifier: str
    terminated: bool
    truncated: bool
    no_submit: bool
    timed_out: bool
    steps_used: int
    trajectory_head: str
    trajectory_path: Path
    submission_path: Path
    receipt_path: Path
    score_report_path: Path
    receipt: dict[str, Any]
    score_report: dict[str, Any]
    security_profile: SecurityProfile
    lifecycle: ProcessLifecycleProof


def run_closed_eval_episode(
    *,
    episode_dir: Path | str,
    policy_argv: Sequence[str],
    policy_id: str,
    artifacts_dir: Path | str,
    cursor_seed: str = "episode",
    env_config_path: Path | str | None = None,
    time_limit_s: float = 60.0,
    merkle_leaf_index: int = 0,
    salt_mode: str = "TEST_FIXTURE",
    reveal_salt_in_receipt: bool = False,
    canary_tokens: Sequence[str] = (),
) -> ClosedEvalRunResult:
    """Execute one complete ``CLOSED_EVAL`` episode across isolated OS subprocesses."""
    ep_path = Path(episode_dir).resolve()
    out_dir = Path(artifacts_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = _verify_public_manifest_before_run(ep_path)
    episode_id = str(manifest["episode_id"])
    truth_commitment = str(manifest["truth_commitment"])

    security_profile = detect_security_profile()
    forbidden_tokens = (
        str(ep_path),
        truth_commitment,
        *canary_tokens,
    )

    recorder = TrajectoryRecorder(
        episode_id=episode_id,
        truth_commitment=truth_commitment,
        cursor_seed=cursor_seed,
    )

    deadline = time.monotonic() + time_limit_s
    env_proc = EnvSubprocess(
        ep_path / "public",
        env_config_path=env_config_path,
        cursor_seed=cursor_seed,
        require_closed_eval=True,
    )
    policy_proc: PolicySubprocess | None = None

    steps_used = 0
    terminated = False
    truncated = False
    no_submit = True
    timed_out = False
    submitted_findings: list[dict[str, Any]] = []
    requested_evidence_ids: set[str] = set()

    try:
        t0_ns = time.monotonic_ns()
        init_obs = env_proc.start(deadline_monotonic=deadline)
        assert_policy_outbound_clean(
            json.dumps(init_obs, ensure_ascii=False),
            extra_forbidden_tokens=forbidden_tokens,
        )
        recorder.record_event(
            event_type="reset",
            action_payload={"event": "reset", "cursor_seed": cursor_seed},
            response_payload=init_obs,
            logical_step=0,
            elapsed_ns=time.monotonic_ns() - t0_ns,
        )

        max_steps = int(init_obs["limits"]["max_steps"])
        submit_counts = bool(init_obs["limits"]["submit_counts_as_step"])
        max_exchanges = max_steps + 8

        policy_masks: list[Path] = [ep_path]
        if env_proc.staged_public_dir is not None:
            policy_masks.append(env_proc.staged_public_dir.parent)
        policy_proc = PolicySubprocess(
            policy_argv,
            include_repo_pythonpath=True,
            forbidden_tokens=forbidden_tokens,
            mask_dirs=policy_masks,
        )
        policy_proc.start()
        policy_proc.send_reset(init_obs)

        exchanges = 0
        while not (terminated or truncated):
            if exchanges >= max_exchanges:
                truncated = True
                break

            req_line, read_status = policy_proc.read_request_line(
                deadline_monotonic=deadline,
                max_bytes=MAX_JSONL_LINE_BYTES,
            )
            if read_status == "timeout":
                timed_out = True
                truncated = True
                break
            if read_status == "eof" or req_line is None:
                truncated = True
                break
            if read_status == "oversized":
                # Forward an oversized marker so env accounts/responds deterministically
                req_line = "x" * (MAX_JSONL_LINE_BYTES + 16)

            exchanges += 1
            step_t0_ns = time.monotonic_ns()
            resp_line, resp_obj = env_proc.step_line(req_line, deadline_monotonic=deadline)
            step_elapsed_ns = time.monotonic_ns() - step_t0_ns

            # Parse request if JSON object for event typing & evidence tracking
            try:
                parsed_req: Any = json.loads(req_line)
            except json.JSONDecodeError:
                parsed_req = {"_malformed_raw": req_line[:256]}

            is_dict_req = isinstance(parsed_req, dict)
            action_block = parsed_req.get("action") if is_dict_req else None
            tool_name = action_block.get("tool") if isinstance(action_block, dict) else None
            req_schema_valid = is_dict_req and len(validate_instance("tool_request", parsed_req)) == 0

            # Mirror TwinLedgerEnv step accounting
            if req_schema_valid and tool_name == "submit":
                if submit_counts and steps_used < max_steps:
                    steps_used += 1
                if resp_obj.get("ok") and isinstance(resp_obj.get("result"), dict):
                    steps_used = int(resp_obj["result"].get("steps_used", steps_used))
                    submitted_findings = list(action_block.get("args", {}).get("findings", []))
                    terminated = True
                    no_submit = False
                    recorder.record_event(
                        event_type="submit",
                        action_payload=parsed_req,
                        response_payload=resp_obj,
                        logical_step=steps_used,
                        raw_request_line=req_line,
                        elapsed_ns=step_elapsed_ns,
                    )
                    policy_proc.send_response(resp_obj)
                    policy_proc.send_terminate("submitted")
                    break
                else:
                    if not resp_obj.get("ok") and (resp_obj.get("error") or {}).get("code") == "LIMIT":
                        truncated = True
                    recorder.record_event(
                        event_type="tool_call",
                        action_payload=parsed_req,
                        response_payload=resp_obj,
                        logical_step=steps_used,
                        raw_request_line=req_line,
                        elapsed_ns=step_elapsed_ns,
                    )
                    policy_proc.send_response(resp_obj)
                    if truncated:
                        policy_proc.send_terminate("truncated")
                        break
                    continue

            # Non-submit or schema-invalid dict request
            err_code = (resp_obj.get("error") or {}).get("code") if not resp_obj.get("ok") else None
            if is_dict_req:
                if steps_used < max_steps:
                    steps_used += 1
                elif err_code == "LIMIT":
                    truncated = True

            # Track requested public IDs for optional experimental grounded score
            if resp_obj.get("ok") and isinstance(resp_obj.get("result"), dict):
                res_data = resp_obj["result"]
                if isinstance(res_data.get("typed_id"), str):
                    requested_evidence_ids.add(res_data["typed_id"])
                if isinstance(res_data.get("id"), str) and ":" in res_data["id"]:
                    requested_evidence_ids.add(res_data["id"])

            recorder.record_event(
                event_type="tool_call",
                action_payload=parsed_req,
                response_payload=resp_obj,
                logical_step=steps_used,
                raw_request_line=req_line,
                elapsed_ns=step_elapsed_ns,
            )
            policy_proc.send_response(resp_obj)

            if err_code == "LIMIT":
                truncated = True
                policy_proc.send_terminate("truncated")
                break

        # Record explicit terminal lifecycle event in hash chain
        terminal_type = "terminate" if terminated else "truncate"
        recorder.record_event(
            event_type=terminal_type,
            action_payload={
                "lifecycle": terminal_type,
                "no_submit": no_submit,
                "timed_out": timed_out,
            },
            response_payload={
                "terminated": terminated,
                "truncated": truncated,
                "steps_used": steps_used,
                "submitted_count": len(submitted_findings),
            },
            logical_step=steps_used,
        )
    finally:
        # STRICT TEARDOWN BARRIER: close Policy & Env processes BEFORE Scorer starts!
        policy_exited_ns = policy_proc.close() if policy_proc is not None else time.monotonic_ns()
        env_exited_ns = env_proc.close()

    assert policy_proc is None or not policy_proc.is_alive, "policy subprocess still alive after close()"
    assert not env_proc.is_alive, "env subprocess still alive after close()"

    trajectory_path = out_dir / f"{episode_id}__{policy_id}.trajectory.jsonl"
    timing_path = out_dir / f"{episode_id}__{policy_id}.timings.json"
    submission_path = out_dir / f"{episode_id}__{policy_id}.submission.json"
    receipt_path = out_dir / f"{episode_id}__{policy_id}.receipt.json"
    score_report_path = out_dir / f"{episode_id}__{policy_id}.score_report.json"

    recorder.write_jsonl(trajectory_path)
    timing_path.write_bytes(canonical_bytes(recorder.diagnostic_timing_log()))

    submission_payload = {
        "schema_version": "1.0.0",
        "episode_id": episode_id,
        "policy_identifier": policy_id,
        "steps_used": steps_used,
        "terminated": terminated,
        "truncated": truncated,
        "no_submit": no_submit,
        "timed_out": timed_out,
        "findings": submitted_findings,
        "requested_evidence_ids": sorted(requested_evidence_ids),
        "isolation_profile": security_profile.to_dict(),
    }
    submission_path.write_bytes(canonical_bytes(submission_payload))

    scorer_res: ScorerProcessResult = run_scorer_subprocess(
        episode_dir=ep_path,
        submission_path=submission_path,
        trajectory_path=trajectory_path,
        policy_id=policy_id,
        output_receipt_path=receipt_path,
        output_score_path=score_report_path,
        env_alive=env_proc.is_alive,
        policy_alive=policy_proc.is_alive,
        env_exited_ns=env_exited_ns,
        policy_exited_ns=policy_exited_ns,
        merkle_leaf_index=merkle_leaf_index,
        salt_mode=salt_mode,
        reveal_salt=reveal_salt_in_receipt,
    )
    if scorer_res.exit_code != 0:
        raise RuntimeError(
            f"post-episode scorer rejected run for {episode_id} (exit_code={scorer_res.exit_code})"
        )

    lifecycle = ProcessLifecycleProof(
        env_started_ns=env_proc.started_ns or 0,
        policy_started_ns=policy_proc.started_ns or 0,
        policy_exited_ns=policy_exited_ns,
        env_exited_ns=env_exited_ns,
        scorer_started_ns=scorer_res.started_ns,
        scorer_exited_ns=scorer_res.exited_ns,
    )
    if not lifecycle.strictly_ordered:
        raise RuntimeError(f"lifecycle ordering invariant failed: {lifecycle.to_dict()}")

    return ClosedEvalRunResult(
        episode_id=episode_id,
        policy_identifier=policy_id,
        terminated=terminated,
        truncated=truncated,
        no_submit=no_submit,
        timed_out=timed_out,
        steps_used=steps_used,
        trajectory_head=recorder.head,
        trajectory_path=trajectory_path,
        submission_path=submission_path,
        receipt_path=receipt_path,
        score_report_path=score_report_path,
        receipt=scorer_res.receipt,
        score_report=scorer_res.score_report,
        security_profile=security_profile,
        lifecycle=lifecycle,
    )


def run_closed_eval_batch(
    *,
    runs: Sequence[tuple[Path | str, Sequence[str], str]],
    artifacts_dir: Path | str,
    salt_mode: str = "TEST_FIXTURE",
    reveal_salt_in_receipt: bool = False,
    time_limit_s: float = 60.0,
) -> tuple[str, list[ClosedEvalRunResult]]:
    """Run multiple ``(episode_dir, policy_argv, policy_id)`` specs and Merkle-seal receipts."""
    out_dir = Path(artifacts_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    initial_results: list[ClosedEvalRunResult] = []
    for idx, (ep_dir, argv, pid) in enumerate(runs):
        res = run_closed_eval_episode(
            episode_dir=ep_dir,
            policy_argv=argv,
            policy_id=pid,
            artifacts_dir=out_dir,
            merkle_leaf_index=idx,
            salt_mode=salt_mode,
            reveal_salt_in_receipt=reveal_salt_in_receipt,
            time_limit_s=time_limit_s,
        )
        initial_results.append(res)

    batch_summary = seal_receipt_batch_subprocess(
        [r.receipt_path for r in initial_results],
        output_summary_path=out_dir / "merkle_batch_summary.json",
    )
    merkle_root = str(batch_summary["merkle_root"])

    # Reload updated receipts containing batch Merkle root + inclusion proofs
    final_results: list[ClosedEvalRunResult] = []
    for r in initial_results:
        updated_receipt = json.loads(r.receipt_path.read_text(encoding="utf-8"))
        final_results.append(
            ClosedEvalRunResult(
                episode_id=r.episode_id,
                policy_identifier=r.policy_identifier,
                terminated=r.terminated,
                truncated=r.truncated,
                no_submit=r.no_submit,
                timed_out=r.timed_out,
                steps_used=r.steps_used,
                trajectory_head=r.trajectory_head,
                trajectory_path=r.trajectory_path,
                submission_path=r.submission_path,
                receipt_path=r.receipt_path,
                score_report_path=r.score_report_path,
                receipt=updated_receipt,
                score_report=r.score_report,
                security_profile=r.security_profile,
                lifecycle=r.lifecycle,
            )
        )
    return merkle_root, final_results


__all__ = [
    "ClosedEvalRunResult",
    "ProcessLifecycleProof",
    "run_closed_eval_batch",
    "run_closed_eval_episode",
]
